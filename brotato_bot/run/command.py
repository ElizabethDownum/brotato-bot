"""CLI: ``prepare --plan FILE | --from-proposal FILE [--target ID]`` and
``collect [RUN_ID | --latest]``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import plain_name, read_json
from brotato_bot.run import collect, prepare, proposal


def _install(plan: dict, target: str | None, p: paths.Paths) -> int:
    try:
        warnings = prepare.prepare(plan, target, p)
    except ValueError as exc:
        print(f"prepare: {exc}")
        return 1
    print(f"Wrote {p.plan_json} (plan_id {plan['plan_id']})")
    print(f"target_challenge {target or '(none)'} -> {p.config_json}")
    for w in warnings:
        print(f"WARNING: {w}")
    return 0


def _from_proposal(path: str, p: paths.Paths) -> int:
    try:
        markdown = Path(path).read_text(encoding="utf-8-sig")
        unlock_state = proposal.load_unlock_state(p.data_dir / "unlock_state.json")
        rows = proposal.load_rows(p.runs_out / "index.json")
    except (OSError, ValueError) as exc:
        print(f"prepare: {exc}")
        return 1
    errors = proposal.validate(markdown, unlock_state, Path(path).name, rows)
    if errors:
        for e in errors:
            print(f"prepare: {e}")
        return 1
    plan = proposal.extract_plan(markdown)
    target = proposal.next_run(markdown)["target"]
    plan["target_challenge"] = target or ""  # the mod prefers the plan's target; pin it
    return _install(plan, target, p)


def _prepare(args: argparse.Namespace) -> int:
    p = paths.load()
    if args.from_proposal:
        if args.target:
            print("prepare: --target comes from the proposal's ## Next run")
            return 1
        return _from_proposal(args.from_proposal, p)
    try:
        plan = read_json(args.plan)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"prepare: cannot read {args.plan}: {exc}")
        return 1
    return _install(plan, args.target, p)


def _collect(args: argparse.Namespace) -> int:
    p = paths.load()
    run_id = args.run_id if args.run_id is not None else collect.latest_run_id(p)
    if not run_id:
        print(f"collect: no run recordings in {p.runs_in}")
        return 1
    try:
        plain_name(run_id)
    except ValueError as exc:
        print(f"collect: bad RUN_ID: {exc}")
        return 1
    try:
        report = collect.collect(run_id, p)
    except (OSError, ValueError) as exc:
        print(f"collect: {exc}")
        return 1
    print(f"Collected {run_id} -> {report}")
    return 0


def _register_prepare(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("prepare", help="write plan.json and the target challenge")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", metavar="FILE", help="plan JSON to install")
    source.add_argument(
        "--from-proposal", metavar="FILE", help="proposal whose plan and ## Next run to install"
    )
    parser.add_argument("--target", default=None, metavar="ID", help="target challenge id")
    parser.set_defaults(func=_prepare)


def _register_collect(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("collect", help="summarize a run recording into runs/")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("run_id", nargs="?", default=None, metavar="RUN_ID")
    group.add_argument("--latest", action="store_true", help="the newest recording (the default)")
    parser.set_defaults(func=_collect)


cli.COMMANDS["prepare"] = _register_prepare
cli.COMMANDS["collect"] = _register_collect
