"""Shape a proposal's plan around its target's goal.

``data/unlock_state.json`` records, for a stat challenge, the stat and the value to reach
(``progress[target].stat`` and ``.value``, e.g. ``stat_speed`` and ``-20`` for ``chal_slow``).
The curated plan rows know nothing about that, so a plan copied from a row pursues the
character's normal build and reaches the goal only by accident (run 1, 2026-10-22, won on
``chal_slow`` without ever lowering speed).

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
- the plan family gains the goal as a suffix (``well-rounded-slow-v1``), so the stagnation
  rule sees a different family from the plain row.

A ``chal_difficulty_<n>`` target raises ``## Next run`` ``- danger:`` to ``n``. A target with
neither a stat nor a difficulty number leaves the file unchanged.

Weapon sets are not selected: the dataset keeps one effect per set bonus, so a set whose
bonus also moves the goal stat (blunt lowers speed) is invisible to it.
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
_DIFFICULTY = re.compile(r"chal_difficulty_(\d+)")
_FENCED_JSON = re.compile(r"```json[ \t]*\n(.*?)```", re.DOTALL)
_DANGER_BULLET = re.compile(r"^(- danger: )(\d+)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Goal:
    target: str
    stat: str = ""  # a stat id, or "" for a non-stat challenge
    value: int = 0  # the threshold for a stat goal
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
    value = value if isinstance(value, int) and not isinstance(value, bool) else 0
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


def shape_plan(plan: dict, goal: Goal, items: list[dict]) -> dict:
    """A deep copy of ``plan`` shaped for ``goal``; unchanged when the goal has no stat."""
    out = json.loads(json.dumps(plan))
    if not goal.stat:
        return out
    body = out["plan"]
    stats = body.setdefault("stats", {})
    others = [abs(float(w)) for k, w in stats.items() if k != goal.stat]
    stats[goal.stat] = goal.sign * (max(others, default=0.0) + DOMINANT_MARGIN)
    bonus = body.setdefault("item_bonus", {})
    bans = body.setdefault("ban_items", [])
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        for e in item.get("effects") or []:
            if e.get("key") != goal.stat:
                continue
            v = e.get("value")
            if not isinstance(v, int | float) or isinstance(v, bool) or v == 0:
                continue
            if v * goal.sign > 0:
                b = min(ITEM_BONUS_CAP, round(ITEM_BONUS_PER_POINT * abs(v), 1))
                bonus[item_id] = max(float(bonus.get(item_id, 0.0)), b)
            elif goal.value == 0 and item_id not in bans:
                bans.append(item_id)
    family, version = _family(str(out["plan_id"]))
    suffix = "-" + goal_slug(goal.target)
    if not family.endswith(suffix):
        family += suffix
    out["plan_id"] = f"{family}-v{version}"
    return out


def shape_markdown(markdown: str, goal: Goal | None, items: list[dict]) -> tuple[str, list[str]]:
    """``markdown`` with its ``## Plan`` block and ``- danger:`` bullet shaped for ``goal``.

    Returns the new text and the list of changes made (empty when nothing changed).
    ValueError when the ``## Plan`` block is missing or malformed."""
    from brotato_bot.run import proposal  # circular at import time

    if goal is None:
        return markdown, []
    changes: list[str] = []
    text = markdown.replace("\r\n", "\n")
    plan = proposal.extract_plan(text)
    shaped = shape_plan(plan, goal, items)
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
        changes.append(f"{goal.stat} weight {w:g} (goal {goal.value:+d}), {n} item bonuses")
        if shaped["plan"].get("ban_items") != plan["plan"].get("ban_items"):
            changes.append(f"{len(shaped['plan']['ban_items'])} banned items")
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
        stats = plan.get("plan", {}).get("stats", {})
        w = stats.get(goal.stat)
        hint = f"run proposal shape FILE (goal {goal.stat} {goal.value:+d})"
        if not isinstance(w, int | float) or isinstance(w, bool) or w * goal.sign <= 0:
            errors.append(f"## Plan: not shaped for {goal.target}: {hint}")
        else:
            others = [abs(float(v)) for k, v in stats.items() if k != goal.stat]
            if abs(float(w)) <= max(others, default=0.0):
                errors.append(
                    f"## Plan: {goal.stat} weight {w:g} is not the plan's largest: {hint}"
                )
    return errors


def load_items(dataset_json: Path) -> list[dict]:
    """The dataset's item list; ValueError naming the fix when it is missing."""
    try:
        data = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"{dataset_json} is missing; run dataset build first") from None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"{dataset_json} has no items list")  # noqa: TRY004
    return [i for i in items if isinstance(i, dict)]


def shape_file(path: Path, unlock_state: dict, items: list[dict]) -> list[str]:
    """Shape the proposal at ``path`` in place; returns the changes made."""
    from brotato_bot.fsutil import atomic_write_text
    from brotato_bot.run import proposal

    markdown = Path(path).read_text(encoding="utf-8-sig")
    run = proposal.next_run(markdown)
    goal = goal_for(run["target"], unlock_state)
    text, changes = shape_markdown(markdown, goal, items)
    if changes:
        atomic_write_text(Path(path), text)
    return changes


def describe(goal: Goal | None, changes: list[str], path: Any) -> str:
    if goal is None:
        return f"nothing to shape in {path}: the target has no stat or difficulty goal"
    if not changes:
        return f"{path} is already shaped for {goal.target}"
    return f"shaped {path} for {goal.target}: " + "; ".join(changes)
