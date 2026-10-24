"""``proposal fit --target ID [--character ID]``: which character and starting weapon suit a goal.

Owner's rule (2026-10-23): a proposal must factor in the character's stats and attributes
and the starting weapon's stats and attributes. For a stat goal (``progress[target]`` in
``data/unlock_state.json``) this ranks:

- every unlocked character (only ``requires_character`` when the target names one) by
  ``need``, the goal still to be supplied by items, sets and level-ups after the character's
  flat start (``shape.character_goal_fit``); a -100% gain modifier on the goal stat is a
  veto and sorts last; ties prefer a character that has a plan row in the mod's
  ``build_plans.gd``;
- the starting weapons in that character's pool that the bot profile has unlocked, by the
  goal bonus of the weapon's sets at 6 weapons, then by a type match with the row's
  ``weapon_type``, then by the row's weight on the weapon's scaling stats.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from brotato_bot import paths
from brotato_bot.run import proposal, shape

BUILD_PLANS = Path("mod") / "Ellie-BrotatoBot" / "shopping" / "build_plans.gd"
FULL_SET = 6  # weapon slots: the set bonus at six weapons is the most a build can hold
_STAT_WEIGHT = re.compile(r'"(\w+)":\s*(-?\d+(?:\.\d+)?)')


def load_rows(build_plans: Path) -> str:
    """The text of ``build_plans.gd``; empty when the file is absent."""
    try:
        return Path(build_plans).read_text(encoding="utf-8")
    except OSError:
        return ""


def plan_row(source: str, character_id: str) -> dict | None:
    """``{weapon_type, stats}`` of the character's row in ``build_plans.gd``, else None."""
    m = re.search(rf'"{re.escape(character_id)}": \{{', source)
    if m is None:
        return None
    depth, i = 1, m.end()
    while i < len(source) and depth:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
    body = source[m.end() : i]
    wt = re.search(r'"weapon_type":\s*"([^"]*)"', body)
    block = re.search(r'"stats":\s*\{(.*?)\}', body, re.DOTALL)
    stats = {k: float(v) for k, v in _STAT_WEIGHT.findall(block.group(1))} if block else {}
    return {"weapon_type": wt.group(1) if wt else "", "stats": stats}


def _goal_tags(goal: shape.Goal, dataset: dict) -> set[str]:
    wanted = {i["id"] for i in shape.goal_data(goal, dataset)["items"]}
    tags: set[str] = set()
    for item in dataset.get("items") or []:
        if isinstance(item, dict) and item.get("id") in wanted:
            tags.update(t for t in item.get("tags") or [] if isinstance(t, str))
    return tags


def rank_characters(
    goal: shape.Goal, dataset: dict, unlock_state: dict, source: str, required: str | None
) -> list[dict]:
    """One row per candidate character, best first."""
    tags = _goal_tags(goal, dataset)
    state = unlock_state.get("characters")
    state = state if isinstance(state, dict) else {}
    rows = []
    for c in dataset.get("characters") or []:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            continue
        cid = c["id"]
        if required is not None and cid != required:
            continue
        if required is None and not (state.get(cid) or {}).get("unlocked"):
            continue
        rows.append(
            {
                "id": cid,
                **shape.character_goal_fit(c, goal),
                "banned": sorted(set(c.get("banned_item_groups") or []) & tags),
                "row": plan_row(source, cid) is not None,
                "economy": shape.bonus_on(c.get("flat_bonuses"), "stat_harvesting", "value") or 0,
                "dlc": c.get("dlc"),
            }
        )
    rows.sort(key=lambda r: (r["veto"], r["need"], not r["row"], r["id"]))
    return rows


def _character_line(r: dict) -> str:
    gain = "none" if r["gain_pct"] is None else f"{r['gain_pct']:+g}%"
    note = ""
    if r["veto"]:
        note = " VETO (gain -100%: changes are nullified)"
    elif r["gain_pct"] not in (None, 0):
        note = f" (start scaled by gain {gain})"
    return (
        f"{r['id']}: base {r['base']:+g}, gain {gain}, need {r['need']:+g}{note}, "
        f"banned {','.join(r['banned']) or '-'}, row {'yes' if r['row'] else 'no'}, "
        f"economy {r['economy']:+g}, dlc {r['dlc'] or '-'}"
    )


def rank_weapons(
    goal: shape.Goal, dataset: dict, unlock_state: dict, character: dict, row: dict | None
) -> tuple[list[dict], bool]:
    """Starting weapons of ``character`` best first, and whether the unlock list exists."""
    lists = unlock_state.get("weapons_unlocked")
    known = isinstance(lists, list)
    set_bonus: dict[str, float] = {}
    for s in shape.goal_data(goal, dataset)["sets"]:
        counts = [c for c in s["by_count"] if c <= FULL_SET]
        if counts:
            set_bonus[s["name"]] = s["by_count"][max(counts)] * goal.sign
    by_name: dict[str, dict] = {}
    for w in dataset.get("weapons") or []:
        if isinstance(w, dict) and isinstance(w.get("id"), str):
            by_name.setdefault(w.get("display_name") or w.get("name"), w)
    weights = (row or {}).get("stats", {})
    out = []
    for name in character.get("starting_weapon_pool") or []:
        w = by_name.get(name)
        if w is None or (known and w["id"] not in lists):
            continue
        sets = [str(x) for x in w.get("sets") or []]
        wt = w.get("weapon_type") or ""
        row_type = (row or {}).get("weapon_type", "")
        out.append(
            {
                "id": w["id"],
                "sets": {x: set_bonus.get(x, 0) for x in sets},
                "goal_bonus": sum(set_bonus.get(x, 0) for x in sets),
                "type": wt,
                "type_match": row is not None and row_type in ("", "any", wt),
                "scaling": sum(weights.get(str(st[0]), 0.0) for st in w.get("scaling_stats") or []),
            }
        )
    out.sort(key=lambda r: (-r["goal_bonus"], not r["type_match"], -r["scaling"], r["id"]))
    return out, known


def _weapon_line(r: dict, has_row: bool) -> str:
    sets = ", ".join(f"{n} {v:+g}" for n, v in r["sets"].items()) or "-"
    match = "yes" if r["type_match"] else ("no" if has_row else "no row")
    return (
        f"{r['id']}: sets [{sets}], goal bonus {r['goal_bonus']:+g}, "
        f"type {r['type']} (match {match}), scaling {r['scaling']:g}"
    )


def fit_lines(
    target: str,
    dataset: dict,
    unlock_state: dict,
    source: str,
    character: str | None = None,
) -> list[str]:
    goal = shape.goal_for(target, unlock_state)
    if goal is None or not goal.stat:
        return [f"no stat goal for {target}"]
    required = unlock_state["progress"][target].get("requires_character")
    lines = [f"Fit for {target}: {goal.stat} to {goal.value:+g} (sign {goal.sign:+d})"]
    if required:
        lines.append(f"{target} requires {required}: the only candidate")
    ranked = rank_characters(goal, dataset, unlock_state, source, required)
    if not ranked:
        return [*lines, "no candidate character (none unlocked in the dataset)"]
    lines.append("Characters (need ascending, vetoes last, plan row first on a tie):")
    lines.extend(f"  {_character_line(r)}" for r in ranked)
    top = ranked[0]
    lines.append(f"Top character: {top['id']}")
    chosen = character or top["id"]
    record = next((c for c in dataset["characters"] if c.get("id") == chosen), None)
    if record is None:
        return [*lines, f"unknown character {chosen}"]
    row = plan_row(source, chosen)
    weapons, known = rank_weapons(goal, dataset, unlock_state, record, row)
    header = f"Starting weapons for {chosen} (set goal bonus at {FULL_SET} weapons, type, scaling)"
    if not known:
        header += "; unlock state lacks weapons_unlocked, treating all as unlocked"
    lines.append(header + ":")
    lines.extend(f"  {_weapon_line(r, row is not None)}" for r in weapons)
    lines.append(f"Top weapon: {weapons[0]['id']}" if weapons else "Top weapon: none unlocked")
    return lines


def _fit(args: argparse.Namespace) -> int:
    p = paths.load()
    try:
        unlock_state = proposal.load_unlock_state(p.data_dir / "unlock_state.json")
        dataset = shape.load_dataset(p.data_dir / "brotato.json")
    except ValueError as exc:
        print(f"proposal: {exc}")
        return 1
    source = load_rows(p.project_root / BUILD_PLANS)
    for line in fit_lines(args.target, dataset, unlock_state, source, args.character):
        print(line)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    fit = sub.add_parser("fit", help="rank characters and starting weapons for a stat goal")
    fit.add_argument("--target", required=True, metavar="ID")
    fit.add_argument("--character", default=None, metavar="ID")
    fit.set_defaults(func=_fit)
