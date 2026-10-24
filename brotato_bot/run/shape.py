"""Shape a proposal's plan around its target's goal.

``data/unlock_state.json`` records, for a stat challenge, the stat and the value to reach
(``progress[target].stat`` and ``.value``, e.g. ``stat_speed`` and ``-20`` for ``chal_slow``).
The curated plan rows know nothing about that, so a plan copied from a row pursues the
character's normal build and reaches the goal only by accident (run 1, 2026-10-22, won on
``chal_slow`` without ever lowering speed).

The mod merges a plan file over the character's built-in row one level deep: ``stats`` and
``item_bonus`` are merged key by key, every other key (``ban_items`` included) is replaced.
So the proposal's ``stats`` must be the character's full row: dominance of the goal weight
only means something over the full map, and ``goal_errors`` requires ``MIN_STATS`` other
weights. ``shape`` never creates ``ban_items`` unless it bans an item, since a present list
would replace the row's own bans.

``shape`` rewrites the proposal's ``## Plan`` block so the plan pursues the goal:

- the goal stat gets the plan's dominant weight, with the goal's sign. The shop scorer
  (``shop_advisor.gd`` ``stat_score``) adds a weight for an item effect that raises a
  weighted stat and subtracts it for one that lowers it, so a negative weight rewards every
  item that lowers the stat and penalises every item that raises it, in the shop and at
  level-ups;
- every item in ``data/brotato.json`` whose effect moves the stat the right way gets an
  ``item_bonus`` of ``ITEM_BONUS_PER_POINT`` per point, capped at ``ITEM_BONUS_CAP``;
- for a goal of exactly 0 (keep the stat at zero) items that move it the other way are
  banned;
- ``min_buy`` is raised to ``MIN_BUY_UNDER_GOAL`` (never lowered), so low-scoring junk is
  harder to buy while a goal needs the gold;
- the plan family gains the goal as a suffix (``well-rounded-slow-v1``), so the stagnation
  rule sees a different family from the plain row.

A ``chal_difficulty_<n>`` target raises ``## Next run`` ``- danger:`` to ``n``. A target with
neither a stat nor a difficulty number leaves the file unchanged.

Shaping may prefer a weapon set (the owner's rulings, 2026-10-23, replacing the 2026-10-22
"never selects a set" hold, which was a complexity hold and not a principle). When a set's
full bonus (at 6 weapons) moves the goal stat by at least ``PREFER_SET_SHARE`` of the
character's ``need`` (what items and level-ups must still supply after the character's flat
start, ``character_goal_fit``), the plan gains ``prefer_sets: {set_id: bonus}``, the bonus
being the set's contribution in goal units times ``ITEM_BONUS_PER_POINT`` (capped at
``ITEM_BONUS_CAP``), and ``weapon_type`` becomes ``any`` so the set's weapons are not typed
out. ``weapon_set``, the hard all-or-nothing gate, is never set by shaping. ``prefer_sets`` is
a soft score term for the mod. The goal data, meaning every item and every weapon-set bonus
that moves the goal stat, is also surfaced: ``goal_data`` collects it and ``brief_lines``
words it for the proposal writer (``proposal shape`` prints it) and for the in-run model (the
decision prompt's Objective).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ITEM_BONUS_PER_POINT = 1.5
ITEM_BONUS_CAP = 30.0
DOMINANT_MARGIN = 4.0
MIN_BUY_UNDER_GOAL = 6.0  # calibrated 2026-10-23 with `brotato_bot score`; see docs/observations.md
FULL_SET = 6  # weapon slots: the set bonus at six weapons is the most a build can hold
PREFER_SET_SHARE = 0.25  # a set must cover this share of the character's need to be preferred
MIN_STATS = 4  # weights besides the goal stat a plan's ``stats`` must carry
_DIFFICULTY = re.compile(r"chal_difficulty_(\d+)")
_FENCED_JSON = re.compile(r"```json[ \t]*\n(.*?)```", re.DOTALL)
_DANGER_BULLET = re.compile(r"^(- danger: )(\d+)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Goal:
    target: str
    stat: str = ""  # a stat id, or "" for a non-stat challenge
    value: int | float = 0  # the threshold for a stat goal
    danger: int | None = None  # the danger a difficulty challenge requires

    @property
    def sign(self) -> int:
        """+1 to raise the stat, -1 to lower it or keep it at zero."""
        return 1 if self.value > 0 else -1


def goal_for(target: str | None, unlock_state: dict) -> Goal | None:
    """The goal a target implies, or None when it has no stat and no difficulty number."""
    if not target:
        return None
    progress = unlock_state.get("progress")
    info = progress.get(target) if isinstance(progress, dict) else None
    info = info if isinstance(info, dict) else {}
    stat = str(info.get("stat") or "")
    value = info.get("value")
    value = value if isinstance(value, int | float) and not isinstance(value, bool) else 0
    m = _DIFFICULTY.fullmatch(target)
    danger = int(m.group(1)) if m else None
    if not stat and danger is None:
        return None
    return Goal(target=target, stat=stat, value=value if stat else 0, danger=danger)


def _family(plan_id: str) -> tuple[str, str]:
    m = re.search(r"-v(\d+)$", plan_id)
    return (plan_id[: m.start()], m.group(1)) if m else (plan_id, "1")


def goal_slug(target: str) -> str:
    return target.removeprefix("chal_").replace("_", "-")


def full_set_bonus(by_count: dict[int, float], sign: int) -> float:
    """The set's goal-stat bonus at ``FULL_SET`` weapons (the highest count not above it) in
    goal units, positive when it moves the stat toward the goal."""
    counts = [c for c in by_count if c <= FULL_SET]
    return by_count[max(counts)] * sign if counts else 0.0


def preferred_sets(goal: Goal, dataset: dict, character: dict | None) -> dict[str, float]:
    """``{set_id: bonus}`` for sets worth at least ``PREFER_SET_SHARE`` of the character's need."""
    fit = character_goal_fit(character, goal)
    if fit["veto"]:
        return {}
    need = fit["need"]
    out: dict[str, float] = {}
    for s in goal_data(goal, dataset)["sets"]:
        bonus = full_set_bonus(s["by_count"], goal.sign)
        if need > 0 and bonus >= PREFER_SET_SHARE * need:
            out[s["id"]] = min(ITEM_BONUS_CAP, round(ITEM_BONUS_PER_POINT * bonus, 1))
    return out


def shape_plan(plan: dict, goal: Goal, items: list[dict], dataset: dict | None = None) -> dict:
    """A deep copy of ``plan`` shaped for ``goal``; unchanged when the goal has no stat.

    With ``dataset`` the plan's character (``plan["character_id"]``) and the weapon sets
    are factored in: see ``preferred_sets``."""
    out = json.loads(json.dumps(plan))
    if not goal.stat:
        return out
    body = out["plan"]
    stats = body.setdefault("stats", {})
    others = [abs(float(w)) for k, w in stats.items() if k != goal.stat]
    stats[goal.stat] = goal.sign * (max(others, default=0.0) + DOMINANT_MARGIN)
    bonus = body.setdefault("item_bonus", {})
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        v = _sum_on(item.get("effects"), goal.stat)  # summed, as goal_data does
        if v == 0:
            continue
        if v * goal.sign > 0:
            b = min(ITEM_BONUS_CAP, round(ITEM_BONUS_PER_POINT * abs(v), 1))
            bonus[item_id] = max(float(bonus.get(item_id, 0.0)), b)
        elif goal.value == 0:
            bans = body.setdefault("ban_items", [])
            if item_id not in bans:
                bans.append(item_id)
    family, version = _family(str(out["plan_id"]))
    suffix = "-" + goal_slug(goal.target)
    if not family.endswith(suffix):
        family += suffix
    body["min_buy"] = max(float(body.get("min_buy", 0)), MIN_BUY_UNDER_GOAL)
    if dataset is not None:
        character = next(
            (c for c in dataset.get("characters") or [] if c.get("id") == out.get("character_id")),
            None,
        )
        prefer = preferred_sets(goal, dataset, character)
        if prefer:
            body["prefer_sets"] = prefer
            body["weapon_type"] = "any"
    out["plan_id"] = f"{family}-v{version}"
    return out


def shape_markdown(
    markdown: str, goal: Goal | None, items: list[dict], dataset: dict | None = None
) -> tuple[str, list[str]]:
    """``markdown`` with its ``## Plan`` block and ``- danger:`` bullet shaped for ``goal``.

    Returns the new text and the list of changes made (empty when nothing changed).
    ValueError when the ``## Plan`` block is missing or malformed."""
    from brotato_bot.run import proposal  # circular at import time

    if goal is None:
        return markdown, []
    changes: list[str] = []
    text = markdown.replace("\r\n", "\n")
    plan = proposal.extract_plan(text)
    shaped = shape_plan(plan, goal, items, dataset)
    if shaped != plan:
        body = proposal._section(text, "## Plan")
        assert body is not None
        new_body = _FENCED_JSON.sub(
            lambda _m: "```json\n" + json.dumps(shaped, indent=2) + "\n```", body, count=1
        )
        text = text.replace(body, new_body, 1)
        w = shaped["plan"]["stats"][goal.stat]
        n = sum(
            1 for k in shaped["plan"]["item_bonus"] if k not in plan["plan"].get("item_bonus", {})
        )
        changes.append(f"{goal.stat} weight {w:g} (goal {goal.value:+g}), {n} item bonuses")
        if shaped["plan"].get("ban_items") != plan["plan"].get("ban_items"):
            changes.append(f"{len(shaped['plan'].get('ban_items', []))} banned items")
        if shaped["plan"]["min_buy"] != plan["plan"].get("min_buy"):
            changes.append(f"min_buy {shaped['plan']['min_buy']:g}")
        if shaped["plan"].get("prefer_sets") != plan["plan"].get("prefer_sets"):
            sets = ", ".join(f"{k} {v:g}" for k, v in shaped["plan"]["prefer_sets"].items())
            changes.append(f"prefer_sets {sets}")
        if shaped["plan"].get("weapon_type") != plan["plan"].get("weapon_type"):
            changes.append(f"weapon_type {shaped['plan']['weapon_type']}")
        if shaped["plan_id"] != plan["plan_id"]:
            changes.append(f"plan_id {shaped['plan_id']}")
    if goal.danger is not None:
        m = _DANGER_BULLET.search(text)
        if m and int(m.group(2)) < goal.danger:
            text = text[: m.start()] + f"{m.group(1)}{goal.danger}" + text[m.end() :]
            changes.append(f"danger {goal.danger}")
    return text, changes


def goal_errors(plan: dict | None, run: dict, unlock_state: dict) -> list[str]:
    """Validator: a plan must be shaped for its target's goal, and danger must suffice."""
    goal = goal_for(run.get("target"), unlock_state)
    if goal is None:
        return []
    errors = []
    if goal.danger is not None and run["danger"] < goal.danger:
        errors.append(
            f"## Next run: target {goal.target} needs danger {goal.danger}, not {run['danger']}"
        )
    if goal.stat and plan is not None:
        prefer = plan.get("plan", {}).get("prefer_sets", {})
        if not isinstance(prefer, dict) or any(
            isinstance(v, bool) or not isinstance(v, int | float) or not 0 < v <= ITEM_BONUS_CAP
            for v in prefer.values()
        ):
            errors.append(
                f"## Plan: prefer_sets must map set ids to bonuses above 0 and at most "
                f"{ITEM_BONUS_CAP:g}"
            )
        stats = plan.get("plan", {}).get("stats", {})
        w = stats.get(goal.stat)
        hint = f"run proposal shape FILE (goal {goal.stat} {goal.value:+g})"
        if not isinstance(w, int | float) or isinstance(w, bool) or w * goal.sign <= 0:
            errors.append(f"## Plan: not shaped for {goal.target}: {hint}")
        else:
            others = [abs(float(v)) for k, v in stats.items() if k != goal.stat]
            if len(others) < MIN_STATS:
                errors.append(
                    f"## Plan: stats has only {len(others)} weights besides {goal.stat}; "
                    "copy the character's full row before shaping"
                )
            if abs(float(w)) <= max(others, default=0.0):
                errors.append(
                    f"## Plan: {goal.stat} weight {w:g} is not the plan's largest: {hint}"
                )
    return errors


def load_dataset(dataset_json: Path) -> dict:
    """The dataset object; ValueError naming the fix when it is missing or malformed."""
    try:
        data = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"{dataset_json} is missing; run dataset build first") from None
    except json.JSONDecodeError:
        raise ValueError(f"{dataset_json} is not valid JSON; run dataset build") from None
    if not isinstance(data, dict):
        raise ValueError(f"{dataset_json} is not a dataset object; run dataset build")  # noqa: TRY004
    return data


def load_items(dataset_json: Path) -> list[dict]:
    """The dataset's item list; ValueError naming the fix when it is missing."""
    items = load_dataset(dataset_json).get("items")
    if not isinstance(items, list):
        raise ValueError(f"{dataset_json} has no items list")  # noqa: TRY004
    return [i for i in items if isinstance(i, dict)]


def _num(v: Any) -> float:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else 0.0


def _sum_on(effects: Any, stat: str) -> float:
    return sum(
        _num(e.get("value")) for e in effects or [] if isinstance(e, dict) and e.get("key") == stat
    )


def bonus_on(rows: Any, stat: str, key: str) -> float | None:
    """The ``key`` value of the entry for ``stat`` in a character's bonus list, else None."""
    for r in rows or []:
        if isinstance(r, dict) and r.get("stat") == stat:
            return _num(r.get(key))
    return None


def character_goal_fit(character: dict | None, goal: Goal) -> dict:
    """What a character's start supplies toward a stat goal.

    The game scales the whole stat, including the flat ``start``, by ``g = 1 + gain/100``
    and checks the challenge against that scaled value. ``veto`` when ``g <= 0`` (Chunky's
    speed: changes are nullified); ``base`` is the raw ``start`` with the goal's sign (a
    -10 speed start on a -20 goal is +10, a +5 start is -5). ``need`` is what items, sets
    and level-ups must still supply in raw units in the goal's direction:
    ``(goal.value / g - start) * goal.sign`` for a non-vetoed character."""
    character = character or {}
    start = bonus_on(character.get("flat_bonuses"), goal.stat, "value") or 0.0
    pct = bonus_on(character.get("gain_modifiers"), goal.stat, "pct")
    g = 1 + (pct or 0) / 100
    veto = g <= 0
    return {
        "start": start,
        "gain_pct": pct,
        "veto": veto,
        "base": start * goal.sign + 0.0,  # + 0.0 turns -0.0 into 0.0
        "need": (goal.value / g - start) * goal.sign
        if not veto
        else (goal.value - start) * goal.sign,
    }


def goal_data(goal: Goal, dataset: dict) -> dict:
    """Every item and weapon-set bonus in ``dataset`` that moves ``goal.stat`` the goal's way."""
    out: dict = {"items": [], "sets": []}
    if not goal.stat:
        return out
    items = []
    for item in dataset.get("items") or []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        total = _sum_on(item.get("effects"), goal.stat)
        if total * goal.sign > 0:
            items.append(
                {
                    "id": item["id"],
                    "value": total,
                    "tier": item.get("tier"),
                    "price": item.get("value"),
                }
            )
    items.sort(key=lambda i: (-abs(i["value"]), i["id"]))
    out["items"] = items
    weapons = [w for w in dataset.get("weapons") or [] if isinstance(w, dict)]
    for s in dataset.get("sets") or []:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str):
            continue
        by_count: dict[int, float] = {}
        for b in s.get("bonuses") or []:
            if not isinstance(b, dict) or not isinstance(b.get("count"), int):
                continue
            total = _sum_on(b.get("effects") or [b.get("effect")], goal.stat)
            if total * goal.sign > 0:
                by_count[b["count"]] = total
        if not by_count:
            continue
        names = {s["id"], s.get("name"), s.get("display_name")}
        types = {
            str(w["weapon_type"])
            for w in weapons
            if w.get("weapon_type") and names & set(w.get("sets") or [])
        }
        out["sets"].append(
            {
                "id": s["id"],
                "name": s.get("name") or s["id"],
                "weapon_types": sorted(types),
                "by_count": dict(sorted(by_count.items())),
            }
        )
    out["sets"].sort(key=lambda s: s["id"])
    return out


def brief_lines(goal: Goal, data: dict) -> list[str]:
    """Plain lines presenting ``goal_data`` to a model; empty when the goal has no stat."""
    if not goal.stat:
        return []
    verb = "raise" if goal.value > 0 else "lower"
    lines = [f"Goal data for {goal.target}: {verb} {goal.stat} to {goal.value:+g}."]
    items = data.get("items") or []
    if items:
        lines.append(
            ", ".join(
                f"{i['id']} {i['value']:+g} (tier {i['tier']}, price {i['price']})" for i in items
            )
        )
    else:
        lines.append(f"No item in the dataset {verb}s {goal.stat}.")
    sets = data.get("sets") or []
    if sets:
        lines.append(
            "; ".join(
                f"{s['id']} ({'/'.join(s['weapon_types'])}): "
                + ", ".join(f"{c} weapons {v:+g}" for c, v in s["by_count"].items())
                for s in sets
            )
        )
    else:
        lines.append(f"No weapon set in the dataset {verb}s {goal.stat}.")
    return lines


def shape_file(
    path: Path, unlock_state: dict, items: list[dict], dataset: dict | None = None
) -> list[str]:
    """Shape the proposal at ``path`` in place; returns the changes made."""
    from brotato_bot.fsutil import atomic_write_text
    from brotato_bot.run import proposal

    markdown = Path(path).read_text(encoding="utf-8-sig")
    run = proposal.next_run(markdown)
    goal = goal_for(run["target"], unlock_state)
    text, changes = shape_markdown(markdown, goal, items, dataset)
    if changes:
        atomic_write_text(Path(path), text)
    return changes


def describe(goal: Goal | None, changes: list[str], path: Any) -> str:
    if goal is None:
        return f"nothing to shape in {path}: the target has no stat or difficulty goal"
    if not changes:
        return f"{path} is already shaped for {goal.target}"
    return f"shaped {path} for {goal.target}: " + "; ".join(changes)
