"""CLI: ``sidecar [--auto-next]``: answer the mod's decision requests (runbook 4.10).

Every ``poll_once`` touches ``<mod_user_dir>/sidecar.alive`` (the mod asks only while
its mtime is under 10 s old), then handles each ``requests/<id>.json`` in name order and
deletes it afterwards, whatever happened (one failing request warns and never stops
the loop):

1. Read the request and ``state/<id>.json`` (the mod names the request after its state
   file; ``state_path`` is a ``user://`` path, so the id locates it). A request that
   cannot be read, whose id or run_id is not a plain name, whose ``deadline_ms`` is not
   a finite number, or whose state file is missing or not a JSON object, is dropped
   with a warning; one whose ``deadline_ms`` (absolute epoch ms) has passed is dropped
   without a call.
2. Build the prompt from the request as written, ``plan.json``, the dataset, unlock
   state, knowledge cache and the latest same-character, same-kind rows of
   ``decisions/experience.jsonl``.
3. Run ``decide_fn`` with the budget left until the deadline, routed by ``screen``: the
   ladder gets a copy of the request whose ``kind`` is its ``screen``, so ``screen:
   checkpoint`` uses ``prompts/checkpoint.md``, ``checkpoint_model`` and
   ``checkpoint_timeout_ms`` whatever the ``kind``.
4. Write ``responses/<id>.json`` atomically when there is a decision; on ``fallback``
   nothing (the mod times out and its rules decide). A checkpoint also renders
   ``runs/<run_id>-checkpoint.md``.
5. Append the decision record to ``decisions/<run_id>.jsonl`` and print
   ``[<id>] <kind> -> <action> via <source> in <ms> ms``.

With ``auto_next`` it also tails the newest ``<mod_user_dir>/runs/*.jsonl``. When an
``end`` line with outcome ``won`` or ``death`` appears in a run whose header ``profile_id`` is the bot profile
(config.json ``bot_profile_id``, default 1), it collects that run and runs ``claude -p /brotato-next`` in the
project (spec 7.5), once per run file, for at most ``NEXT_TIMEOUT_S``. Requests wait
meanwhile and the heartbeat goes stale, so the mod's rules decide until it returns.
Runs that ended before the sidecar started are left alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import (
    atomic_write_json,
    atomic_write_text,
    plain_name,
    read_json,
    read_json_or_empty,
)
from brotato_bot.report import render
from brotato_bot.run import collect
from brotato_bot.run.prepare import bot_profile_id
from brotato_bot.sidecar import decide, experience, prompt
from brotato_bot.sidecar.command import _now_ms, prompt_inputs

ALIVE_FILE = "sidecar.alive"
NEXT_MODEL = "claude-sonnet-5-5"
NEXT_TIMEOUT_S = 600


def _header_profile(run_file: Path) -> object:
    """The ``profile_id`` in the run file's first (header) line, None without one."""
    try:
        with run_file.open("rb") as fh:
            header = json.loads(fh.readline())
    except (OSError, ValueError):
        return None
    return header.get("profile_id") if isinstance(header, dict) else None


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
        for req_file in sorted(self.paths.requests_dir.glob("*.json")):
            try:
                self._handle(req_file)
            except Exception as exc:  # noqa: BLE001 -- one bad request must not stop the loop
                print(f"WARNING: [{req_file.stem}] request failed: {type(exc).__name__}: {exc}")
            finally:
                self._delete(req_file)
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
        """Answer one request; ``poll_once`` deletes it afterwards."""
        started = self.clock()
        rid = req_file.stem
        try:
            plain_name(rid)
            request = read_json(req_file)
            if not isinstance(request, dict):
                raise TypeError("not a JSON object")
            run_id = plain_name(request.get("run_id"))
            deadline = request["deadline_ms"]
            if (
                not isinstance(deadline, (int, float))
                or isinstance(deadline, bool)
                or not math.isfinite(deadline)
            ):
                raise TypeError(f"deadline_ms is not a finite number: {deadline!r}")
        except (OSError, ValueError, TypeError, KeyError) as exc:  # JSONDecodeError: ValueError
            print(f"WARNING: [{rid}] unreadable request deleted: {type(exc).__name__}: {exc}")
            return
        kind = str(request.get("kind") or "?")
        if deadline - _now_ms() <= 0:
            print(f"[{rid}] {kind} deadline passed {_now_ms() - int(deadline)} ms ago; deleted")
            return

        p = self.paths
        try:
            state = read_json(p.state_dir / f"{rid}.json")
            if not isinstance(state, dict):
                raise TypeError("not a JSON object")
        except (OSError, ValueError, TypeError) as exc:
            print(f"WARNING: [{rid}] no usable state file; request deleted: {exc}")
            return
        plan = read_json_or_empty(p.plan_json)
        past = experience.query(
            p.decisions_dir / "experience.jsonl", str(state.get("character_id") or ""), kind
        )
        user = prompt.build(request, state, plan, experience=past, **prompt_inputs(p))
        screen = str(request.get("screen") or kind)
        ladder_request = {**request, "kind": screen}
        outcome = self.decide_fn(
            ladder_request, user, self.cfg, deadline_ms=int(deadline - _now_ms())
        )
        elapsed_ms = int((self.clock() - started) * 1000)

        if outcome.decision is not None:
            try:
                atomic_write_json(p.responses_dir / f"{rid}.json", outcome.decision)
            except OSError as exc:
                print(f"WARNING: [{rid}] cannot write the response: {exc}")
        checkpoint = screen == "checkpoint"
        if checkpoint:
            note = render.checkpoint_report(run_id, state, plan, outcome.decision, outcome.source)
            atomic_write_text(p.runs_out / f"{run_id}-checkpoint.md", note)
        experience.append(
            p.decisions_dir / f"{run_id}.jsonl",
            {
                "id": rid,
                "kind": kind,
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "model": self.cfg["checkpoint_model" if checkpoint else "model"],
                "source": outcome.source,
                "attempts": outcome.to_dict()["attempts"],
                "elapsed_ms": elapsed_ms,
                # ``decision`` and ``response`` duplicate on purpose (UNION ruling).
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
                if event.get("outcome") not in collect.END_OUTCOMES:
                    print(f"auto-next: {newest.stem} skipped: ended {event.get('outcome')!r}")
                    return
                profile, bot_pid = _header_profile(newest), bot_profile_id(self.cfg)
                if profile != bot_pid:
                    print(f"auto-next: {newest.stem} skipped: profile {profile} is not "
                          f"the bot profile ({bot_pid})")  # fmt: skip
                    return
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
            result = subprocess.run(
                cmd, check=False, cwd=self.paths.project_root, timeout=NEXT_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            print(f"WARNING: auto-next: /brotato-next timed out after {NEXT_TIMEOUT_S} s")
            return
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
    sidecar = Sidecar(p, read_json_or_empty(p.config_json), auto_next=args.auto_next)
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
