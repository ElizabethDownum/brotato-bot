"""Deterministic between-run stagnation verdict for a target challenge.

Reads the ``runs/index.json`` rows (see ``collect.index_row``). Only finished runs
(``win`` or ``death``) on the target that were played on the bot profile count: a row whose
``profile_id`` is present and is not 1 (the owner's own runs) is ignored, while a row with
no ``profile_id`` key (written before the key existed) is kept. The window is the last
``window`` counted runs.

- fewer than ``window`` finished runs -> ``fresh``
- a run whose ``target_fired`` is true in the window -> ``progressing``. A win that did not
  fire the target is not progress on it: the bot can win every run and still never reach
  the goal (run 1, 2026-10-22, won on ``chal_slow`` without lowering speed).
- no later run beats the first run -> ``stagnant``. A run beats the first when it died at a
  later wave, or at the same wave with more end HP (a missing value reads as 0). A win
  never beats anything: surviving to the end is not progress on the target either.
- otherwise -> ``progressing``
- ``escalate``: the window is stagnant, a material change (plan family or character) landed
  at run k with the window starting at or after k, the ``window`` runs before k were
  stagnant, and no run since k beats the first run after the change.
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
BOT_PROFILE_ID = 1


@dataclass(frozen=True)
class Verdict:
    state: str  # "fresh" | "progressing" | "stagnant" | "escalate"
    reason: str
    runs_considered: list[str] = field(default_factory=list)


def _family(plan_id: str | None) -> str:
    return re.sub(r"-v\d+$", "", plan_id or "")


def _n(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _ids(run: list[dict]) -> str:
    return ", ".join(str(r.get("run_id")) for r in run)


def _waves(run: list[dict]) -> str:
    return ", ".join("?" if r.get("death_wave") is None else str(r["death_wave"]) for r in run)


def _bot_row(r: object) -> bool:
    return isinstance(r, dict) and ("profile_id" not in r or r["profile_id"] == BOT_PROFILE_ID)


def finished_runs(rows: list[dict], target: str) -> list[dict]:
    """The finished bot-profile rows on ``target``, oldest first."""
    return [
        r
        for r in rows
        if _bot_row(r) and r.get("target_challenge") == target and r.get("outcome") in FINISHED
    ]


def _success(r: dict) -> bool:
    return r.get("target_fired") is True


def _beats(r: dict, first: dict) -> bool:
    if r.get("outcome") == "win":
        return False
    wave, wave0 = _n(r.get("death_wave")), _n(first.get("death_wave"))
    return wave > wave0 or (
        wave == wave0 and _n(r.get("hp_end_last_wave")) > _n(first.get("hp_end_last_wave"))
    )


def _stagnant(run: list[dict]) -> bool:
    """True when no run in ``run`` succeeded and no later run beats the first."""
    if any(_success(r) for r in run):
        return False
    return not any(_beats(r, run[0]) for r in run[1:])


def _change(prev: dict, cur: dict) -> str | None:
    """A description of the material change from ``prev`` to ``cur``, or None."""
    parts = []
    if _family(prev.get("plan_id")) != _family(cur.get("plan_id")):
        parts.append(f"plan {_family(prev.get('plan_id'))} -> {_family(cur.get('plan_id'))}")
    if prev.get("character_id") != cur.get("character_id"):
        parts.append(f"character {prev.get('character_id')} -> {cur.get('character_id')}")
    return ", ".join(parts) or None


def verdict(rows: list[dict], target: str, window: int = 3) -> Verdict:
    finished = finished_runs(rows, target)
    if len(finished) < window:
        return Verdict("fresh", f"{len(finished)} finished run(s) on {target}; need {window}")

    last = finished[-window:]
    ids = [str(r.get("run_id")) for r in last]
    fired = [r for r in last if r.get("target_fired") is True]
    if fired:
        return Verdict("progressing", f"the target fired in run {fired[-1].get('run_id')}", ids)
    if not _stagnant(last):
        return Verdict(
            "progressing",
            "a later run beat the first run's death wave (or its end HP at the same wave): "
            f"deaths at waves {_waves(last)}",
            ids,
        )

    start = len(finished) - window
    for k in range(start, window - 1, -1):
        change = _change(finished[k - 1], finished[k])
        before, since = finished[k - window : k], finished[k:]
        if change and _stagnant(before) and _stagnant(since):
            return Verdict(
                "escalate",
                f"{change} at run {finished[k].get('run_id')}; runs {_ids(since)} died at waves "
                f"{_waves(since)} with none beating the first; runs {_ids(before)} before it "
                f"died at waves {_waves(before)} with none beating the first",
                ids,
            )
    return Verdict(
        "stagnant",
        f"{window} deaths at waves {_waves(last)} with none beating the first run's death wave "
        "(or its end HP at the same wave)",
        ids,
    )


def mark_paused(targets_md: Path, target: str, proposal: Path, today: date) -> bool:
    """Append the paused line for ``target`` to ``targets_md``, keeping existing content.

    Idempotent: when a line starting ``paused: <target> `` is already there, nothing is
    written and the result is False. True when the line was appended."""
    path = Path(targets_md)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if any(line.startswith(f"paused: {target} ") for line in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"paused: {target} since {today.isoformat()}, evidence in {proposal}\n"
    atomic_write_text(path, text)
    return True


def resolve_target(rows: list[dict], target: str | None = None) -> str | None:
    """``target`` when given, else the target of the newest finished bot-profile row that
    has one, else None."""
    if target:
        return target
    for r in reversed(rows):
        if _bot_row(r) and r.get("outcome") in FINISHED and r.get("target_challenge"):
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
    target = resolve_target(rows, args.target)
    if target is None:
        if args.mark_paused:
            print("stagnation: --mark-paused needs a target with finished runs")
            return 1
        print("fresh: no runs on any target")
        return 0
    v = verdict(rows, target)
    line = f"{v.state} ({target}): {v.reason}"
    if v.runs_considered:
        line += f" [runs: {', '.join(v.runs_considered)}]"
    print(line)
    if args.mark_paused:
        if v.state != "escalate":
            print(f"stagnation: --mark-paused refused: verdict is {v.state}, not escalate")
            return 1
        targets_md = p.project_root / "targets.md"
        if mark_paused(targets_md, target, Path(args.mark_paused), date.today()):
            print(f"paused: {target} recorded in {targets_md}")
        else:
            print(f"already paused: {target}")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stagnation", help="stagnation verdict for a target")
    parser.add_argument(
        "--target",
        default=None,
        metavar="ID",
        help="target challenge (default: the newest finished bot-profile run's)",
    )
    parser.add_argument(
        "--mark-paused",
        default=None,
        metavar="PROPOSAL_PATH",
        help="append a paused line to targets.md citing this proposal (once per target)",
    )
    parser.set_defaults(func=_stagnation)


cli.COMMANDS["stagnation"] = register
