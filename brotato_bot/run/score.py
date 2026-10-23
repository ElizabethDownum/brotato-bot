"""Score every shop item under a plan, to calibrate ``min_buy``.

The in-game scorer is ``mod/Ellie-BrotatoBot/shopping/effect_score.gd``; it is the source of
truth and ``UNITS`` / ``MAX_UNITS`` / ``effect_score`` here mirror it (a test compares the
constants). The plan weight is the priority per unit of a stat, a unit being the game's
tier-1 level-up value of that stat. Weapons are out of scope.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from brotato_bot import cli, paths
from brotato_bot.run import proposal, shape

UNITS = {
    "stat_max_hp": 3.0,
    "stat_hp_regeneration": 2.0,
    "stat_lifesteal": 1.0,
    "stat_percent_damage": 5.0,
    "stat_melee_damage": 2.0,
    "stat_ranged_damage": 1.0,
    "stat_elemental_damage": 1.0,
    "stat_attack_speed": 5.0,
    "stat_crit_chance": 3.0,
    "stat_engineering": 2.0,
    "stat_range": 15.0,
    "stat_armor": 1.0,
    "stat_dodge": 3.0,
    "stat_speed": 3.0,
    "stat_luck": 5.0,
    "stat_harvesting": 5.0,
    "stat_accuracy": 4.0,
    "stat_crit_damage": 10.0,
    "stat_damage": 1.0,
}
MAX_UNITS = 4.0


def effect_score(
    effects: list[dict],
    weights: dict[str, float],
    boost_stats: dict[str, float] | None = None,
    harvest_capped: bool = False,
) -> float:
    boost_stats = boost_stats or {}
    total = 0.0
    for e in effects or []:
        if not isinstance(e, dict) or e.get("key") not in weights:
            continue
        key = e["key"]
        v = shape._num(e.get("value"))
        if v == 0:
            continue
        w = float(weights[key])
        if key in boost_stats:
            w *= float(boost_stats[key])
        if key == "stat_harvesting" and harvest_capped:
            w *= 0.15
        cap = 1.0 if str(e.get("text_key") or "") else MAX_UNITS
        units = min(abs(v) / UNITS.get(key, 1.0), cap)
        total += (1.0 if v > 0 else -1.0) * w * units
    return total


def item_score(item: dict, plan: dict) -> float:
    """The shop's score for a non-weapon item: effects plus the plan's ``item_bonus``."""
    bonus = plan.get("item_bonus", {}).get(item["id"], 0.0)
    return effect_score(item.get("effects"), plan.get("stats", {})) + float(bonus)


def _summary(effects: Any) -> str:
    return " ".join(
        f"{e['key']}:{shape._num(e.get('value')):+g}"
        for e in effects or []
        if isinstance(e, dict) and isinstance(e.get("key"), str)
    )


def render(items: list[dict], plan: dict, min_buy: float) -> list[str]:
    rows = sorted(((item_score(i, plan), i) for i in items), key=lambda r: (-r[0], r[1]["id"]))
    lines = [f"{'score':>8}  {'id':<34} tier  price  effects"]
    for s, i in rows:
        lines.append(
            f"{s:8.2f}  {i['id']:<34} {i.get('tier')!s:>4} {i.get('value')!s:>6}  "
            + _summary(i.get("effects"))
        )
    above = sum(1 for s, _ in rows if s > min_buy)
    lines.append(f"{above} of {len(rows)} items score above min_buy {min_buy:g}")
    return lines


def _score(args: argparse.Namespace) -> int:
    try:
        if args.plan:
            plan_file = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
        else:
            plan_file = proposal.extract_plan(Path(args.proposal).read_text(encoding="utf-8-sig"))
        body = plan_file["plan"]
        items = shape.load_items(paths.load().data_dir / "brotato.json")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"score: {exc}")
        return 1
    min_buy = args.min_buy if args.min_buy is not None else float(body.get("min_buy", 0))
    print(f"plan {plan_file.get('plan_id')} scored as given (not merged over the built-in row)")
    print("\n".join(render(items, body, min_buy)))
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("score", help="score every item under a plan")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--plan", metavar="FILE", help="plan JSON, as prepare --plan takes it")
    src.add_argument("--proposal", metavar="FILE", help="proposal whose ## Plan block to score")
    parser.add_argument("--min-buy", type=float, default=None, help="default: the plan's min_buy")
    parser.set_defaults(func=_score)


cli.COMMANDS["score"] = register
