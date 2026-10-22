"""CLI: ``prepare --plan FILE [--target ID]`` and ``collect [RUN_ID | --latest]``."""

from __future__ import annotations

import argparse
import json

from brotato_bot import cli, paths
from brotato_bot.fsutil import read_json
from brotato_bot.run import collect, prepare


def _prepare(args: argparse.Namespace) -> int:
    p = paths.load()
    try:
        plan = read_json(args.plan)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"prepare: cannot read {args.plan}: {exc}")
        return 1
    try:
        warnings = prepare.prepare(plan, args.target, p)
    except ValueError as exc:
        print(f"prepare: {exc}")
        return 1
    print(f"Wrote {p.plan_json} (plan_id {plan['plan_id']})")
    print(f"target_challenge {args.target or '(none)'} -> {p.config_json}")
    for w in warnings:
        print(f"WARNING: {w}")
    return 0


def _collect(args: argparse.Namespace) -> int:
    p = paths.load()
    run_id = args.run_id or collect.latest_run_id(p)
    if not run_id:
        print(f"collect: no run recordings in {p.runs_in}")
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
    parser.add_argument("--plan", required=True, metavar="FILE", help="plan JSON to install")
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
