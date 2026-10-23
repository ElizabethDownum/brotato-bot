"""CLI: ``decide-once STATE_FILE [--kind shop|levelup|checkpoint] [--plan FILE]
[--print-prompt]``, ``decide-validate [FILE|-] [--state STATE_FILE --kind KIND]`` and
``advise-context [STATE_FILE]``.

``decide-once`` builds a request from a state file (options from its shop slots or
level-up options), the prompt from the real dataset, cached knowledge and no experience,
runs the validation ladder once (real ``claude`` calls) and prints the ``Outcome`` as JSON.
``decide-validate`` checks an answer (a bare decision object) against the schema and,
with a state, against that screen's actions and options.
``advise-context`` prints the prompt context (no answer format) for an ``advise`` state:
both the shop and the level-up options, no past decisions. Without a path it reads the
newest ``kind: advise`` file in the state directory.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import read_json, read_json_or_empty
from brotato_bot.knowledge import cache
from brotato_bot.sidecar import decide, prompt, schema

DEADLINE_MS = {"checkpoint": "checkpoint_timeout_ms"}


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


ADVISE_KIND = "advise"


def _shop_options(state: dict) -> list[dict]:
    return [
        {"index": i, "id": s.get("id"), "kind": s.get("kind"), "price": s.get("price"),
         "score": s.get("advisor_score", s.get("score"))}
        for i, s in enumerate(state.get("shop") or [])
        if isinstance(s, dict)
    ]  # fmt: skip


def _levelup_options(state: dict) -> list[dict]:
    return [
        {"index": i, "id": u.get("id"), "stat": u.get("stat"), "value": u.get("value"),
         "score": u.get("advisor_score", u.get("score"))}
        for i, u in enumerate(state.get("levelup_options") or [])
        if isinstance(u, dict)
    ]  # fmt: skip


def request_from_state(state: dict, state_path: Path, kind: str, cfg: dict) -> dict:
    """A request as the mod writes one, with ``options`` built from the state file and an
    absolute ``deadline_ms`` (epoch ms) one request timeout from now. An ``advise`` request
    lists the shop offers then the level-up offers, renumbered into one ``index`` sequence."""
    if kind == "shop":
        options = _shop_options(state)
    elif kind == "levelup":
        options = _levelup_options(state)
    elif kind == ADVISE_KIND:
        combined = _shop_options(state) + _levelup_options(state)
        options = [dict(o, index=i) for i, o in enumerate(combined)]
    else:
        options = []
    run_id = str(state.get("run_id") or "decide-once")
    seq = int(state.get("seq") or 0)
    return {
        "id": f"{run_id}-{seq:03}",
        "kind": kind,
        "screen": kind,
        "run_id": run_id,
        "seq": seq,
        "state_path": str(state_path),
        "options": options,
        "deadline_ms": _now_ms() + cfg[DEADLINE_MS.get(kind, "request_timeout_ms")],
    }


def prompt_inputs(p: paths.Paths) -> dict:
    """The ``prompt.build`` inputs every request shares, read from disk now:
    ``dataset``, ``unlock_state`` and ``knowledge`` (each empty when missing)."""
    return {
        "dataset": read_json_or_empty(p.data_dir / "brotato.json"),
        "unlock_state": read_json_or_empty(p.data_dir / "unlock_state.json"),
        "knowledge": cache.load_all(p.knowledge_cache),
    }


class _CommandError(Exception):
    """A failure that advise-context reports as one ``advise-context: <message>`` line."""


@dataclass(frozen=True)
class _Assembled:
    request: dict
    cfg: dict
    user: str
    warnings: list[str]


def _assemble(
    p: paths.Paths,
    state: dict,
    state_path: Path,
    kind: str,
    plan: dict,
    *,
    answer_format: bool = True,
) -> _Assembled:
    """The request, cfg and prompt for one state, shared by decide-once and advise-context.
    The dataset WARNING is returned rather than printed, so each caller orders its output."""
    cfg = decide.settings(read_json_or_empty(p.config_json))
    request = request_from_state(state, state_path, kind, cfg)
    inputs = prompt_inputs(p)
    warnings = []
    if not inputs["dataset"]:
        warnings.append(
            f"WARNING: no dataset at {p.data_dir / 'brotato.json'}; options lack records"
        )
    user = prompt.build(
        request,
        state,
        plan,
        inputs["dataset"],
        inputs["unlock_state"],
        inputs["knowledge"],
        [],
        **({} if answer_format else {"answer_format": False}),  # the default call is unchanged
    )
    return _Assembled(request, cfg, user, warnings)


def _newest_advise_state(state_dir: Path) -> Path | None:
    """The most recently modified ``*.json`` in ``state_dir`` whose ``kind`` is ``advise``.
    A file that is unreadable, not UTF-8 or not JSON is skipped."""
    if not state_dir.is_dir():
        return None
    found: list[tuple[float, Path]] = []
    for f in state_dir.glob("*.json"):
        try:
            data = read_json(f)
            mtime = f.stat().st_mtime
        except (OSError, ValueError):  # ValueError covers bad JSON and bad UTF-8
            continue
        if isinstance(data, dict) and data.get("kind") == ADVISE_KIND:
            found.append((mtime, f))
    return max(found, key=lambda pair: pair[0])[1] if found else None


def _decide_once(args: argparse.Namespace) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # a piped Windows stdout is cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = paths.load()
    try:
        state = read_json(args.state)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"decide-once: cannot read {args.state}: {exc}")
        return 1
    plan_path = Path(args.plan) if args.plan else p.plan_json
    plan = read_json_or_empty(plan_path)
    if args.plan and not plan:
        print(f"decide-once: cannot read plan {args.plan}")
        return 1
    built = _assemble(p, state, Path(args.state), args.kind, plan)
    for line in built.warnings:
        print(line)
    if args.print_prompt:
        print(built.user)
        return 0
    start = time.monotonic()
    outcome = decide.decide(
        built.request, built.user, built.cfg, deadline_ms=built.request["deadline_ms"] - _now_ms()
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(json.dumps(outcome.to_dict(), indent=2, ensure_ascii=False))
    print(f"{built.request['id']} {args.kind} -> {outcome.source} in {elapsed_ms} ms")
    return 0 if outcome.decision is not None else 1


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "decide-once", help="run the decision ladder once on a state file (real CLI calls)"
    )
    parser.add_argument("state", metavar="STATE_FILE", help="exported state JSON")
    parser.add_argument("--kind", choices=["shop", "levelup", "checkpoint"], default="shop")
    parser.add_argument(
        "--plan", default=None, metavar="FILE", help="plan JSON (default plan.json)"
    )
    parser.add_argument(
        "--print-prompt", action="store_true", help="print the user message and exit (no call)"
    )
    parser.set_defaults(func=_decide_once)


def _decide_validate(args: argparse.Namespace) -> int:
    source = args.file
    try:
        raw = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
        text = raw.decode("utf-8-sig")  # UTF-8 whatever the locale; a BOM is dropped
    except (OSError, UnicodeDecodeError) as exc:
        print(f"decide-validate: cannot read {source}: {exc}")
        return 1
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"decide-validate: not JSON: {exc}")
        return 1
    request = None
    if args.state or args.kind:
        if not (args.state and args.kind):
            print("decide-validate: --state and --kind must be given together")
            return 1
        try:
            state = read_json(args.state)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"decide-validate: cannot read {args.state}: {exc}")
            return 1
        if not isinstance(state, dict):
            print(f"decide-validate: {args.state} is not a JSON object")
            return 1
        # request_from_state reads the deadline from cfg, so the defaults are needed here.
        request = request_from_state(state, Path(args.state), args.kind, decide.settings({}))
    errors = schema.validate(answer, request)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("ok")
    return 0


def register_validate(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "decide-validate",
        help="validate a decision answer (JSON) against the schema, and a state's screen",
    )
    parser.add_argument(
        "file", nargs="?", default="-", metavar="FILE|-", help="answer JSON (default: stdin)"
    )
    parser.add_argument("--state", default=None, metavar="STATE_FILE", help="exported state JSON")
    parser.add_argument("--kind", choices=["shop", "levelup", "checkpoint"], default=None)
    parser.set_defaults(func=_decide_validate)


def _advise_text(state_arg: str | None) -> str:
    """The whole advise-context output, built before anything is printed."""
    p = paths.load()
    if state_arg:
        state_path = Path(state_arg)
    else:
        found = _newest_advise_state(p.state_dir)
        if found is None:
            raise _CommandError(f"no advise state file in {p.state_dir}")
        state_path = found
    try:
        state = read_json(state_path)
    except (OSError, ValueError) as exc:
        raise _CommandError(f"cannot read {state_path}: {exc}") from exc
    if not isinstance(state, dict):
        raise _CommandError(f"{state_path} is not a JSON object")
    character = state.get("character_id")
    if not isinstance(character, str) or not character:
        raise _CommandError(f"{state_path} needs a non-empty string character_id")
    wave = state.get("wave")
    if not isinstance(wave, int) or isinstance(wave, bool):
        raise _CommandError(f"{state_path} needs an integer wave")
    plan = read_json_or_empty(p.plan_json)
    try:
        built = _assemble(p, state, state_path, ADVISE_KIND, plan, answer_format=False)
    except Exception as exc:
        raise _CommandError(f"cannot build the context from {state_path}: {exc}") from exc
    header = [f"# State file: {state_path}", f"# Advice dir: {p.advice_dir}"]
    return "\n".join([*header, *built.warnings, built.user])


def _advise_context(args: argparse.Namespace) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # a piped Windows stream is cp1252
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        text = _advise_text(args.state)
    except _CommandError as exc:
        print(f"advise-context: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - any other failure gives one error line
        print(f"advise-context: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(text)
    return 0


def register_advise(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "advise-context", help="print the advice prompt context for an advise state file"
    )
    parser.add_argument(
        "state",
        nargs="?",
        default=None,
        metavar="STATE_FILE",
        help="exported advise state JSON (default: newest kind=advise file in the state dir)",
    )
    parser.set_defaults(func=_advise_context)


cli.COMMANDS["decide-once"] = register
cli.COMMANDS["decide-validate"] = register_validate
cli.COMMANDS["advise-context"] = register_advise
