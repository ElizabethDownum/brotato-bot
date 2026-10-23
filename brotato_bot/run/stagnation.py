"""Deterministic between-run stagnation verdict for a target challenge.

Reads the ``runs/index.json`` rows (see ``collect.index_row``). Only finished runs
(``win`` or ``death``) on the target count. The window is the last ``window`` of them.

- fewer than ``window`` finished runs -> ``fresh``
- a win in the window -> ``progressing``
- no later run beats the first run's death wave or end HP -> ``stagnant``
- otherwise -> ``progressing``
- ``escalate``: the window is stagnant, a material change (plan family or character) landed
  at run k with the window starting at or after k, and the ``window`` runs before k were
  stagnant by the same test.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.fsutil import atomic_write_text, read_json

FINISHED = ("win", "death")


@dataclass(frozen=True)
class Verdict:
    state: str  # "fresh" | "progressing" | "stagnant" | "escalate"
    reason: str
    runs_considered: list[str] = field(default_factory=list)


def _family(plan_id: str | None) -> str:
    return re.sub(r"-v\d+$", "", plan_id or "")


def _n(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _waves(run: list[dict]) -> str:
    return ", ".join("?" if r.get("death_wave") is None else str(r["death_wave"]) for r in run)


def _stagnant(run: list[dict]) -> bool:
    """True when every later run in ``run`` has no better death wave or end HP than the first."""
    if any(r.get("outcome") == "win" for r in run):
        return False
    first = run[0]
    return all(
        _n(r.get("death_wave")) <= _n(first.get("death_wave"))
        and _n(r.get("hp_end_last_wave")) <= _n(first.get("hp_end_last_wave"))
        for r in run[1:]
    )


def _change(prev: dict, cur: dict) -> str | None:
    """A description of the material change from ``prev`` to ``cur``, or None."""
    parts = []
    if _family(prev.get("plan_id")) != _family(cur.get("plan_id")):
        parts.append(f"plan {_family(prev.get('plan_id'))} -> {_family(cur.get('plan_id'))}")
    if prev.get("character_id") != cur.get("character_id"):
        parts.append(f"character {prev.get('character_id')} -> {cur.get('character_id')}")
    return ", ".join(parts) or None


def verdict(rows: list[dict], target: str, window: int = 3) -> Verdict:
    finished = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("target_challenge") == target
        and r.get("outcome") in FINISHED
    ]
    if len(finished) < window:
        return Verdict("fresh", f"{len(finished)} finished run(s) on {target}; need {window}")

    last = finished[-window:]
    ids = [str(r.get("run_id")) for r in last]
    if any(r.get("outcome") == "win" for r in last):
        return Verdict("progressing", f"a win in the last {window} runs", ids)
    if not _stagnant(last):
        return Verdict(
            "progressing",
            f"a later run beat the first run's death wave or end HP: deaths at waves {_waves(last)}",
            ids,
        )

    start = len(finished) - window
    for k in range(start, window - 1, -1):
        change = _change(finished[k - 1], finished[k])
        if change and _stagnant(finished[k - window : k]):
            run_id = finished[k].get("run_id")
            return Verdict(
                "escalate",
                f"{change} at run {run_id}, then {window} more deaths at waves {_waves(last)} "
                f"with no better HP; {window} flat deaths before it",
                ids,
            )
    return Verdict("stagnant", f"{window} deaths at waves {_waves(last)} with no better HP", ids)


def mark_paused(targets_md: Path, target: str, proposal: Path, today: date) -> None:
    """Append the paused line for ``target`` to ``targets_md``, keeping existing content."""
    path = Path(targets_md)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"paused: {target} since {today.isoformat()}, evidence in {proposal}\n"
    atomic_write_text(path, text)


def _newest_target(rows: list[dict]) -> str | None:
    for r in reversed(rows):
        if isinstance(r, dict) and r.get("outcome") in FINISHED and r.get("target_challenge"):
            return r["target_challenge"]
    return None


def _stagnation(args: argparse.Namespace) -> int:
    p = paths.load()
    index = p.runs_out / "index.json"
    try:
        rows = read_json(index) if index.is_file() else []
    except (OSError, json.JSONDecodeError) as exc:
        print(f"stagnation: cannot read {index}: {exc}")
        return 1
    if not isinstance(rows, list):
        print(f"stagnation: {index} is not a JSON list")
        return 1
    target = args.target or _newest_target(rows)
    if target is None:
        if args.mark_paused:
            print("stagnation: --mark-paused needs a target with finished runs")
            return 1
        print("fresh: no runs on any target")
        return 0
    v = verdict(rows, target)
    line = f"{v.state}: {v.reason}"
    if v.runs_considered:
        line += f" [runs: {', '.join(v.runs_considered)}]"
    print(line)
    if args.mark_paused:
        targets_md = p.project_root / "targets.md"
        mark_paused(targets_md, target, Path(args.mark_paused), date.today())
        print(f"paused: {target} recorded in {targets_md}")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stagnation", help="stagnation verdict for a target")
    parser.add_argument(
        "--target",
        default=None,
        metavar="ID",
        help="target challenge (default: newest finished run's)",
    )
    parser.add_argument(
        "--mark-paused",
        default=None,
        metavar="PROPOSAL_PATH",
        help="append a paused line to targets.md citing this proposal",
    )
    parser.set_defaults(func=_stagnation)


cli.COMMANDS["stagnation"] = register
