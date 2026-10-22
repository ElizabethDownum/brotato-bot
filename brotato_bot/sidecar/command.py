"""CLI: ``decide-once STATE_FILE [--kind shop|levelup|checkpoint] [--plan FILE]
[--print-prompt]``.

Builds a request from a state file (options from its shop slots or level-up options),
the prompt from the real dataset, cached knowledge and no experience, runs the
validation ladder once (real ``claude`` calls) and prints the ``Outcome`` as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import read_json, read_json_or_empty
from brotato_bot.knowledge import cache
from brotato_bot.sidecar import decide, prompt

DEADLINE_MS = {"checkpoint": "checkpoint_timeout_ms"}


def request_from_state(state: dict, state_path: Path, kind: str, cfg: dict) -> dict:
    """A request as the mod writes one, with ``options`` built from the state file."""
    if kind == "shop":
        options = [
            {"index": i, "id": s.get("id"), "kind": s.get("kind"), "price": s.get("price"),
             "score": s.get("advisor_score", s.get("score"))}
            for i, s in enumerate(state.get("shop") or [])
            if isinstance(s, dict)
        ]  # fmt: skip
    elif kind == "levelup":
        options = [
            {"index": i, "id": u.get("id"), "stat": u.get("stat"), "value": u.get("value"),
             "score": u.get("advisor_score", u.get("score"))}
            for i, u in enumerate(state.get("levelup_options") or [])
            if isinstance(u, dict)
        ]  # fmt: skip
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
        "deadline_ms": cfg[DEADLINE_MS.get(kind, "request_timeout_ms")],
    }


def prompt_inputs(p: paths.Paths) -> dict:
    """The ``prompt.build`` inputs every request shares, read from disk now:
    ``dataset``, ``unlock_state`` and ``knowledge`` (each empty when missing)."""
    return {
        "dataset": read_json_or_empty(p.data_dir / "brotato.json"),
        "unlock_state": read_json_or_empty(p.data_dir / "unlock_state.json"),
        "knowledge": cache.load_all(p.knowledge_cache),
    }


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
    cfg = decide.settings(read_json_or_empty(p.config_json))
    request = request_from_state(state, Path(args.state), args.kind, cfg)
    inputs = prompt_inputs(p)
    if not inputs["dataset"]:
        print(f"WARNING: no dataset at {p.data_dir / 'brotato.json'}; options lack records")
    user = prompt.build(
        request, state, plan, inputs["dataset"], inputs["unlock_state"], inputs["knowledge"], []
    )
    if args.print_prompt:
        print(user)
        return 0
    start = time.monotonic()
    outcome = decide.decide(request, user, cfg, deadline_ms=request["deadline_ms"])
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(json.dumps(outcome.to_dict(), indent=2, ensure_ascii=False))
    print(f"{request['id']} {args.kind} -> {outcome.source} in {elapsed_ms} ms")
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


cli.COMMANDS["decide-once"] = register
