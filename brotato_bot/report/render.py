"""Render a RunSummary as markdown through ``templates/run.md.tmpl``, and a sidecar
checkpoint through ``templates/checkpoint.md.tmpl`` (both ``str.format``)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from brotato_bot.run.models import MaterialRow, RunSummary

TEMPLATE = Path(__file__).parent / "templates" / "run.md.tmpl"
CHECKPOINT_TEMPLATE = TEMPLATE.with_name("checkpoint.md.tmpl")
NONE = "_none_"


class MaterialSnapshot(MaterialRow):
    floor_values: list[float] = Field(default_factory=list)
    unattached: list[float] = Field(default_factory=list)


class ReportSummary(RunSummary):
    """Run summary with wave-end counters and optional snapshot value samples."""

    materials: list[MaterialSnapshot] = Field(default_factory=list)
    wave_materials: dict[int, dict[str, float | None]] = Field(default_factory=dict)
    trees: dict[int, dict[str, float | None]] = Field(default_factory=dict)


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
    targets = "".join(
        f"; target {cid} fired on wave {wave if wave is not None else '?'}"
        for cid, wave in s.target_waves.items()
    )
    return f"**Outcome:** {text}{hp}{targets}."


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
    if s.build is None:
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
    s = (
        summary
        if isinstance(summary, ReportSummary)
        else ReportSummary.model_validate(summary.model_dump())
    )
    outcomes = outcomes or {}
    danger = s.danger if s.danger is not None else "?"
    plan_section = "\n".join(
        [
            f"- Character: {s.character_id or '?'} (danger {danger})",
            f"- Plan: {s.plan_id or '?'}",
            f"- Target challenge: {s.target_challenge or 'none'}",
        ]
    )
    if s.launch is not None:
        plan_section += (
            f"\n\nlaunched by the mod: {s.launch.get('character_id')}, "
            f"{s.launch.get('starting_weapon')}, danger {s.launch.get('danger')}"
        )
    waves = _table(
        ["wave", "hp", "gold", "dmg", "kills", "speed"],
        [
            (w.wave, w.hp_end, w.gold_end, w.damage_taken, w.kills, w.stats.get("stat_speed", ""))
            for w in s.waves
        ],
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
        ["kind", "action", "source", "confidence", "rulings", "rationale", "outcome"],
        [
            (
                d.kind,
                d.action,
                d.source,
                d.confidence,
                (
                    f"approve {sum(r.get('verdict') == 'approve' for r in d.rulings)}, "
                    f"decline {sum(r.get('verdict') == 'decline' for r in d.rulings)}, "
                    f"missing {d.rulings_missing if d.rulings_missing is not None else '-'}"
                )
                if d.rulings or d.rulings_missing is not None
                else None,
                d.rationale,
                outcomes.get(d.id, ""),
            )
            for d in s.decisions
        ],
    )
    notes = "".join(f"- {n}\n" for n in s.notes)
    # Keep the established sections unchanged for recordings without the new events.
    telemetry = []
    if s.offers:
        telemetry.append(
            "## Offers\n\n"
            + _table(
                ["wave", "view", "gold", "items (id tier price score; * goal)", "bought"],
                [
                    (
                        r.wave,
                        r.view,
                        r.gold,
                        "; ".join(
                            f"{i.get('id', '?')}{'*' if i.get('id') in s.goal_items else ''} "
                            + " ".join(_cell(i.get(k)) for k in ("tier", "price", "score"))
                            for i in r.items
                        ),
                        ", ".join(r.bought),
                    )
                    for r in s.offers
                ],
            )
        )
    if s.crates:
        telemetry.append(
            "## Crates\n\n"
            + _table(
                ["wave", "item", "action", "score", "source"],
                [(r.wave, r.item, r.action, r.score, r.source) for r in s.crates],
            )
        )
    if s.build is not None:
        telemetry.append(
            "## Build\n\n"
            + "\n".join(
                f"- {key.capitalize()}: "
                + (", ".join(f"{item} x{count}" for item, count in Counter(values).items()) or "-")
                for key, values in s.build.items()
            )
        )
    if s.wave_materials:
        rows = []
        swept = []
        collected = []
        for wave, m in sorted(s.wave_materials.items()):
            before, after = m.get("bag_before"), m.get("bag_after")
            sweep = after - before if before is not None and after is not None else None
            swept.append(sweep)
            collected.append(m.get("collected_value"))
            rows.append(
                (
                    wave,
                    m.get("floor_count"),
                    m.get("floor_value"),
                    before,
                    after,
                    sweep,
                    m.get("collected_value") if m.get("collected_value") is not None else "",
                )
            )
        rows.append(
            (
                "Run total",
                "",
                "",
                "",
                s.wave_materials[max(s.wave_materials)].get("bag_after"),
                sum(swept) if all(v is not None for v in swept) else "",
                sum(collected) if all(v is not None for v in collected) else "",
            )
        )
        telemetry.append(
            "## Materials\n\n"
            + _table(
                [
                    "wave",
                    "floor count",
                    "floor value",
                    "bag before",
                    "bag after",
                    "swept",
                    "collected value",
                ],
                rows,
            )
            + "\n\nRun total: bag after is the bag left at the end of the run; swept and"
            + " collected value are totals (blank when any wave is unknown)."
            + "\n\nThe bag pays out only through newly spawned pickups and the floor is capped"
            + " at 50 pickups, so a growing bag before means unspent value."
        )
    if s.materials and (
        not s.wave_materials or any(r.floor_values or r.unattached for r in s.materials)
    ):
        floors = [v for r in s.materials for v in r.floors]
        extra = any(r.floor_values or r.unattached for r in s.materials)
        floor_values = [v for r in s.materials for v in r.floor_values]
        unattached = [v for r in s.materials for v in r.unattached]

        def means(values, loose):
            return (
                (
                    sum(values) / len(values) if values else "",
                    sum(loose) / len(loose) if loose else "",
                )
                if extra
                else ()
            )

        rows = [
            (
                r.wave,
                sum(r.floors) / len(r.floors) if r.floors else None,
                max(r.floors, default=None),
                r.bag if r.bag is not None else "",
                *means(r.floor_values, r.unattached),
            )
            for r in s.materials
        ]
        rows.append(
            (
                "Run total",
                sum(floors) / len(floors) if floors else None,
                max(floors, default=None),
                sum(r.bag or 0 for r in s.materials),
                *means(floor_values, unattached),
            )
        )
        telemetry.append(
            ("## Material snapshots\n\n" if s.wave_materials else "## Materials\n\n")
            + _table(
                ["wave", "mean floor", "max floor", "bag swept at wave end"]
                + (["mean floor value", "mean unattached"] if extra else []),
                rows,
            )
            + "\n\nRun total: snapshot-weighted floor mean, floor maximum, sum of swept bag."
            + " Bag swept at wave end is the maximum bag in the following wave's snapshots;"
            + " blank when unavailable (including the last wave)."
        )
    if s.trees:
        felled = [t.get("felled") for t in s.trees.values()]
        telemetry.append(
            "## Trees\n\n"
            + _table(
                ["wave", "spawned", "felled", "alive"],
                [
                    (wave, t.get("spawned"), t.get("felled"), t.get("alive"))
                    for wave, t in sorted(s.trees.items())
                ]
                + [
                    ("Run total", "", sum(felled) if all(v is not None for v in felled) else "", "")
                ],
            )
        )
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
    ) + ("\n" + "\n\n".join(telemetry) + "\n" if telemetry else "")


def _list(values: list) -> str:
    return ", ".join(str(v) for v in values) or "none"


def checkpoint_report(
    run_id: str, state: dict, plan: dict, decision: dict | None, source: str
) -> str:
    """``runs/<run_id>-checkpoint.md`` for a checkpoint request: the state at the
    checkpoint, and the sidecar's ``decision`` (None on ``fallback``) as a proposal."""
    target = state.get("target_challenge") or plan.get("target_challenge") or "none"
    hp = f", HP {state['hp']}/{state.get('max_hp')}" if state.get("hp") is not None else ""
    achieved = "\n".join(
        [
            f"- Target challenge: {target}",
            f"- Challenges completed this run: {_list(state.get('unlocks_this_run') or [])}",
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
            f"- Weapons: {_list(weapons)}",
            f"- Items: {_list(items)}",
            f"- Stats: {_list(stats)}",
            f"- Plan in effect: {state.get('plan_id') or plan.get('plan_id') or '?'}",
        ]
    )
    if decision is None:
        revision = f"None: no decision ({source}); the mod times out and keeps the plan."
    elif decision.get("action") == "revise_plan":
        patch = json.dumps(decision.get("plan_patch"), indent=2, ensure_ascii=False)
        revision = (
            f"`revise_plan` (confidence {decision.get('confidence')}) with this proposed "
            f"plan patch; the run's checkpoint event records whether the mod applied it:"
            f"\n\n```json\n{patch}\n```"
        )
    else:
        revision = (
            f"None: `{decision.get('action')}` (confidence {decision.get('confidence')}); "
            "no plan change proposed."
        )
    return CHECKPOINT_TEMPLATE.read_text(encoding="utf-8").format(
        run_id=run_id,
        wave=state.get("wave") if state.get("wave") is not None else "?",
        achieved=achieved,
        remaining=remaining,
        plan_revision=revision,
        rationale=(decision or {}).get("rationale") or NONE,
    )
