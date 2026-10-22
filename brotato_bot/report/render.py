"""Render a RunSummary as markdown through ``templates/run.md.tmpl`` (``str.format``)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from brotato_bot.run.models import RunSummary

TEMPLATE = Path(__file__).parent / "templates" / "run.md.tmpl"
NONE = "_none_"


def _cell(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    rows = list(rows)
    if not rows:
        return NONE
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _outcome_line(s: RunSummary) -> str:
    if s.outcome == "win":
        text = "won"
    elif s.outcome == "death":
        text = f"died on wave {s.death_wave}" if s.death_wave is not None else "died"
    else:
        text = f"incomplete (end line: {s.end_outcome or 'missing'})"
    last = s.hp_end_last_wave
    hp = f"; HP {last} at the end of the last completed wave" if last is not None else ""
    return f"**Outcome:** {text}{hp}."


def _death_section(s: RunSummary) -> str:
    d = s.death
    if d is None:
        return NONE
    killer = f", killed by {d.killer}" if d.killer else ""
    lines = [f"Died on wave {d.wave}{killer}.", ""]
    if d.dmg_w is not None:
        lines.append(f"- Damage taken that wave: {d.dmg_w}")
    if d.last_threats:
        lines.append(f"- Nearest threats: {', '.join(d.last_threats)}")
    lines.append(f"- Weapons: {', '.join(d.weapons) or '-'}")
    lines.append(f"- Items: {', '.join(d.items) or '-'}")
    if d.position is not None:
        lines.append(f"- Position: {d.position}")
    return "\n".join(lines)


def _challenges_section(s: RunSummary) -> str:
    lines = []
    for c in s.challenges:
        mark = " (target)" if c in s.targets_completed or c == s.target_challenge else ""
        lines.append(f"- {c}{mark}")
    out = "\n".join(lines) if lines else NONE
    if s.checkpoints:
        out += "\n\nTarget checkpoint:\n\n" + _table(
            ["wave", "id", "action", "applied", "reason"],
            [(c.wave, c.id or None, c.action, c.applied, c.reason or None) for c in s.checkpoints],
        )
    return out


def run_report(summary: RunSummary, outcomes: dict[str, str] | None = None) -> str:
    s = summary
    outcomes = outcomes or {}
    danger = s.danger if s.danger is not None else "?"
    plan_section = "\n".join(
        [
            f"- Character: {s.character_id or '?'} (danger {danger})",
            f"- Plan: {s.plan_id or '?'}",
            f"- Target challenge: {s.target_challenge or 'none'}",
        ]
    )
    waves = _table(
        ["wave", "hp", "gold", "dmg", "kills"],
        [(w.wave, w.hp_end, w.gold_end, w.damage_taken, w.kills) for w in s.waves],
    )
    if any(not w.completed for w in s.waves):
        waves += "\n\nThe death wave has no wave_end line: hp is 0, kills unknown."
    shop = _table(
        ["wave", "action", "item", "price", "score", "source"],
        [(r.wave, r.action, r.item, r.price, r.score, r.source) for r in s.shop],
    )
    levelups = _table(
        ["wave", "picked", "score", "source", "alternatives"],
        [
            (r.wave, r.picked, r.score, r.source, ", ".join(r.alternatives) or None)
            for r in s.levelups
        ],
    )
    decisions = _table(
        ["kind", "action", "source", "confidence", "rationale", "outcome"],
        [
            (d.kind, d.action, d.source, d.confidence, d.rationale, outcomes.get(d.id, ""))
            for d in s.decisions
        ],
    )
    notes = "".join(f"- {n}\n" for n in s.notes)
    return TEMPLATE.read_text(encoding="utf-8").format(
        run_id=s.run_id,
        outcome_line=_outcome_line(s),
        notes=notes + "\n" if notes else "",
        plan_section=plan_section,
        waves_table=waves,
        shop_table=shop,
        levelups_table=levelups,
        decisions_table=decisions,
        death_section=_death_section(s),
        challenges_section=_challenges_section(s),
    )
