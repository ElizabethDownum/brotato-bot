"""CLI: ``sidecar [--auto-next]``: answer the mod's decision requests (runbook 4.10).

Every ``poll_once`` touches ``<mod_user_dir>/sidecar.alive`` (the mod asks only while
its mtime is under 10 s old), then handles each ``requests/<id>.json`` in name order:

1. Read the request and ``state/<id>.json`` (the mod names the request after its state
   file; ``state_path`` is a ``user://`` path, so the id locates it). A request that
   cannot be read, or whose id or run_id is not a plain name, is deleted with a warning;
   one whose ``deadline_ms`` (absolute epoch ms) has passed is deleted without a call.
2. Build the prompt from ``plan.json``, the dataset, unlock state, knowledge cache and
   the latest same-character, same-kind records of ``decisions/<run_id>.jsonl``.
3. Run ``decide_fn`` with the budget left until the deadline. ``screen: checkpoint``
   uses ``prompts/checkpoint.md``, ``checkpoint_model`` and ``checkpoint_timeout_ms``.
4. Write ``responses/<id>.json`` atomically when there is a decision; on ``fallback``
   nothing (the mod times out and its rules decide). A checkpoint also renders
   ``runs/<run_id>-checkpoint.md``.
5. Append the decision record to ``decisions/<run_id>.jsonl``, print
   ``[<id>] <kind> -> <action> via <source> in <ms> ms`` and delete the request.

With ``auto_next`` it also tails the newest ``<mod_user_dir>/runs/*.jsonl``. When an
``end`` line appears it collects that run and runs ``claude -p /brotato-next`` in the
project (spec 7.5), once per run file. Runs that ended before the sidecar started are
left alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import atomic_write_json, atomic_write_text, plain_name, read_json
from brotato_bot.report import render
from brotato_bot.run import collect
from brotato_bot.sidecar import decide, experience, prompt
from brotato_bot.sidecar.command import _read_optional, prompt_inputs

ALIVE_FILE = "sidecar.alive"
EXPERIENCE_ROWS = 20
NEXT_MODEL = "claude-sonnet-5-5"
CHECKPOINT_TEMPLATE = render.TEMPLATE.with_name("checkpoint.md.tmpl")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _fmt_list(values: list) -> str:
    return ", ".join(str(v) for v in values) or "none"


def checkpoint_note(run_id: str, state: dict, plan: dict, outcome: decide.Outcome) -> str:
    """``runs/<run_id>-checkpoint.md`` for a checkpoint request's outcome."""
    target = state.get("target_challenge") or plan.get("target_challenge") or "none"
    hp = f", HP {state['hp']}/{state.get('max_hp')}" if state.get("hp") is not None else ""
    achieved = "\n".join(
        [
            f"- Target challenge: {target}",
            f"- Challenges completed this run: {_fmt_list(state.get('unlocks_this_run') or [])}",
            f"- Wave {state.get('wave')}{hp}, gold {state.get('gold')}",
        ]
    )
    weapons = [w.get("id") for w in state.get("weapons") or [] if isinstance(w, dict)]
    items = [
        f"{i.get('id')} x{i.get('count', 1)}"
        for i in state.get("items") or []
        if isinstance(i, dict)
    ]
    stats = [f"{k} {v}" for k, v in sorted((state.get("stats") or {}).items()) if v]
    remaining = "\n".join(
        [
            f"- Weapons: {_fmt_list(weapons)}",
            f"- Items: {_fmt_list(items)}",
            f"- Stats: {_fmt_list(stats)}",
            f"- Plan in effect: {state.get('plan_id') or plan.get('plan_id') or '?'}",
        ]
    )
    d = outcome.decision
    if d is None:
        revision = f"None: no decision ({outcome.source}); the mod times out and keeps the plan."
    elif d.get("action") == "revise_plan":
        patch = json.dumps(d.get("plan_patch"), indent=2, ensure_ascii=False)
        revision = (
            f"`revise_plan` (confidence {d.get('confidence')}), merged into plan.json by the "
            f"mod:\n\n```json\n{patch}\n```"
        )
    else:
        revision = (
            f"None: `{d.get('action')}` (confidence {d.get('confidence')}); "
            "the plan continues unchanged."
        )
    return CHECKPOINT_TEMPLATE.read_text(encoding="utf-8").format(
        run_id=run_id,
        wave=state.get("wave") if state.get("wave") is not None else "?",
        achieved=achieved,
        remaining=remaining,
        plan_revision=revision,
        rationale=(d or {}).get("rationale") or render.NONE,
    )


class Sidecar:
    def __init__(
        self,
        paths: paths.Paths,
        cfg: dict | None,
        decide_fn=decide.decide,
        clock=time.monotonic,
        *,
        auto_next: bool = False,
    ) -> None:
        self.paths = paths
        self.cfg = decide.settings(cfg)
        self.cfg.setdefault("next_model", NEXT_MODEL)
        self.decide_fn = decide_fn
        self.clock = clock
        self.auto_next = auto_next
        self.alive = paths.mod_user_dir / ALIVE_FILE
        self._next_done: set[str] = set()
        newest = self._newest_run() if auto_next else None
        # (run file, bytes already read): a run file present at start is read from its end.
        self._tail = (newest, newest.stat().st_size if newest else 0)

    # --- request loop ---------------------------------------------------------

    def poll_once(self) -> int:
        """Touch the heartbeat, handle every pending request and, with ``auto_next``,
        check the newest run file for its end. Returns the number of requests handled."""
        self._heartbeat()
        handled = 0
        if self.paths.requests_dir.is_dir():
            for req_file in sorted(self.paths.requests_dir.glob("*.json")):
                self._handle(req_file)
                self._heartbeat()
                handled += 1
        if self.auto_next:
            self._check_run_end()
        return handled

    def run_forever(self, poll_interval_s: float = 0.25) -> None:
        """Poll until interrupted; the heartbeat file is removed on the way out so the mod
        stops asking at once."""
        try:
            while True:
                self.poll_once()
                time.sleep(poll_interval_s)
        finally:
            self.alive.unlink(missing_ok=True)

    def _heartbeat(self) -> None:
        self.alive.parent.mkdir(parents=True, exist_ok=True)
        self.alive.touch()

    def _delete(self, req_file: Path) -> None:
        try:
            req_file.unlink(missing_ok=True)
        except OSError as exc:
            print(f"WARNING: cannot delete {req_file}: {exc}")

    def _handle(self, req_file: Path) -> None:
        started = self.clock()
        rid = req_file.stem
        try:
            plain_name(rid)
            request = read_json(req_file)
            if not isinstance(request, dict):
                raise TypeError("not a JSON object")
            run_id = plain_name(request.get("run_id"))
            deadline = request["deadline_ms"]
            if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
                raise TypeError(f"deadline_ms is not a number: {deadline!r}")
        except (OSError, ValueError, TypeError, KeyError) as exc:  # JSONDecodeError: ValueError
            print(f"WARNING: [{rid}] unreadable request deleted: {type(exc).__name__}: {exc}")
            self._delete(req_file)
            return
        kind = str(request.get("kind") or "?")
        if deadline - _now_ms() <= 0:
            print(f"[{rid}] {kind} deadline passed {_now_ms() - int(deadline)} ms ago; deleted")
            self._delete(req_file)
            return

        p = self.paths
        state = _read_optional(p.state_dir / f"{rid}.json")
        plan = _read_optional(p.plan_json)
        log = p.decisions_dir / f"{run_id}.jsonl"
        past = experience.query(log, str(state.get("character_id") or ""), kind, EXPERIENCE_ROWS)
        user = prompt.build(request, state, plan, experience=past, **prompt_inputs(p))
        outcome = self.decide_fn(request, user, self.cfg, deadline_ms=int(deadline - _now_ms()))
        elapsed_ms = int((self.clock() - started) * 1000)

        if outcome.decision is not None:
            try:
                atomic_write_json(p.responses_dir / f"{rid}.json", outcome.decision)
            except OSError as exc:
                print(f"WARNING: [{rid}] cannot write the response: {exc}")
        screen = request.get("screen") or kind
        checkpoint = screen == "checkpoint"
        if checkpoint:
            note = p.runs_out / f"{run_id}-checkpoint.md"
            atomic_write_text(note, checkpoint_note(run_id, state, plan, outcome))
        experience.append(
            log,
            {
                "id": rid,
                "kind": kind,
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "model": self.cfg["checkpoint_model" if checkpoint else "model"],
                "source": outcome.source,
                "attempts": outcome.to_dict()["attempts"],
                "elapsed_ms": elapsed_ms,
                "decision": outcome.decision,
                "prompt_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                "run_id": run_id,
                "screen": screen,
                "character_id": state.get("character_id"),
                "wave": state.get("wave"),
                "options": request.get("options"),
                "response": outcome.decision,
            },
        )
        action = (outcome.decision or {}).get("action") or "fallback"
        print(f"[{rid}] {kind} -> {action} via {outcome.source} in {elapsed_ms} ms")
        self._delete(req_file)

    # --- auto-next ------------------------------------------------------------

    def _newest_run(self) -> Path | None:
        run_id = collect.latest_run_id(self.paths)
        return self.paths.runs_in / f"{run_id}.jsonl" if run_id else None

    def _check_run_end(self) -> None:
        newest = self._newest_run()
        if newest is None:
            return
        path, offset = self._tail
        if newest != path:
            offset = 0
        try:
            with newest.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
        except OSError:
            return
        complete = chunk.rfind(b"\n") + 1  # a line still being written waits for the next poll
        self._tail = (newest, offset + complete)
        if newest.stem in self._next_done:
            return
        for line in chunk[:complete].splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("kind") == "end":
                self._next_done.add(newest.stem)
                self._run_next(newest.stem)
                return

    def _run_next(self, run_id: str) -> None:
        try:
            report = collect.collect(run_id, self.paths)
        except (OSError, ValueError) as exc:
            print(f"WARNING: auto-next: collect {run_id} failed: {exc}")
            return
        print(f"auto-next: collected {run_id} -> {report}; running /brotato-next")
        cmd = ["claude", "-p", "--model", self.cfg["next_model"], "/brotato-next"]
        try:
            result = subprocess.run(cmd, check=False, cwd=self.paths.project_root)
        except OSError as exc:
            print(f"WARNING: auto-next: cannot run claude: {exc}")
            return
        print(f"auto-next: /brotato-next exited with code {result.returncode}")


def _sidecar(args: argparse.Namespace) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # a piped Windows stdout is cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = paths.load()
    if not (p.data_dir / "brotato.json").is_file():
        print(f"WARNING: no dataset at {p.data_dir / 'brotato.json'}; options lack records")
    sidecar = Sidecar(p, _read_optional(p.config_json), auto_next=args.auto_next)
    print(
        f"sidecar: answering {p.requests_dir} (auto-next {'on' if args.auto_next else 'off'}); "
        "Ctrl+C stops"
    )
    try:
        sidecar.run_forever()
    except KeyboardInterrupt:
        print("sidecar: stopped")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sidecar", help="answer the mod's decision requests")
    parser.add_argument(
        "--auto-next",
        action="store_true",
        help="at each run's end, collect it and run /brotato-next (real claude call)",
    )
    parser.set_defaults(func=_sidecar)


cli.COMMANDS["sidecar"] = register
