"""Decision response schema shared with the mod and the Claude CLI.

``decision.schema.json`` is specialized per request for structured output. The
strict ``ShopDecision`` contract requires rulings; ``validate`` explicitly tolerates
missing/malformed board rulings so a usable action survives, just as in the mod.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator, with_config

SCHEMA_PATH = Path(__file__).with_name("decision.schema.json")

Action = Literal["buy", "reroll", "lock", "pass", "skip", "pick", "take", "recycle", "revise_plan"]
NEEDS_OPTION_INDEX = frozenset({"buy", "lock", "pass", "pick"})
# The actions each screen applies (base_shop.gd, upgrades_ui.gd, Checkpoint.wanted).
SCREEN_ACTIONS = {
    "shop": ("buy", "lock", "pass", "reroll", "skip", "revise_plan"),
    "levelup": ("pick",),
    "crate": ("take", "recycle"),
    "checkpoint": ("revise_plan", "skip"),
}

# Plan keys whose values the mod uses as ints (plan_file.gd INT_PLAN_KEYS).
INT_PLAN_KEYS = ("harvest_cap", "max_weapons", "reroll_keep", "max_rerolls", "gold_floor")
_PATCH_CONFIG = ConfigDict(extra="forbid", strict=True)


@with_config(_PATCH_CONFIG)
class PhaseBoost(TypedDict, total=False):
    until_wave: int
    stats: dict[str, float]


@with_config(_PATCH_CONFIG)
class Steering(TypedDict, total=False):
    tree_value: float
    sweep: float
    sweep_radius: float
    gold_value: float
    stand_continuity: float
    tree_policy: Literal["auto", "seek", "preserve"]


@with_config(_PATCH_CONFIG)
class PlanPatch(TypedDict, total=False):
    """The plan keys the mod reads (shopping/build_plans.gd, shop_advisor.gd, base_shop.gd),
    with the types it reads them as. The mod's PlanFile.KEY_TYPES is the same table."""

    weapon_type: Literal["ranged", "melee", "any"]
    stats: dict[str, float]
    item_bonus: dict[str, float]
    phase_boost: PhaseBoost
    steering: Steering
    harvest_cap: int
    max_weapons: int
    reroll_keep: int
    max_rerolls: int
    gold_floor: int
    min_buy: float
    prefer_weapons: list[str]
    ban_items: list[str]
    deprioritize_weapons: list[str]
    ask_on: list[str]
    weapon_set: str
    unique_weapons: bool
    stack_combine: bool
    hitrate_pref: bool
    spend_surplus: bool


class Ruling(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    option_index: int = Field(ge=0)
    verdict: Literal["approve", "decline"]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Action
    option_index: int | None = Field(default=None, ge=0)
    rulings: list[Ruling] | None = None
    plan_patch: PlanPatch | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=300)
    tags: list[str]

    @model_validator(mode="after")
    def _conditional_fields(self) -> "Decision":
        # Optional fields may be omitted but, as in the JSON Schema, not sent as null.
        for name in ("option_index", "plan_patch", "rulings"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        if self.action in NEEDS_OPTION_INDEX and self.option_index is None:
            raise ValueError(f"option_index is required for action '{self.action}'")
        if self.action in ("take", "recycle") and "option_index" in self.model_fields_set:
            raise ValueError(f"option_index must be omitted for action '{self.action}'")
        if self.action == "revise_plan" and self.plan_patch is None:
            raise ValueError("plan_patch is required for action 'revise_plan'")
        return self


class ShopDecision(Decision):
    """The strict published shop contract; runtime tolerance is explicit below."""

    rulings: list[Ruling]


def screen_for(request: dict) -> str | None:
    screen = request.get("screen") or request.get("kind")
    # Legacy shop pivot requests did not carry screen. Level-up pivots do.
    return "shop" if screen == "pivot" else screen


def normalize_rulings(raw: Any, indexes: list[int] | None = None) -> list[dict]:
    """Match DecisionClient: ignore bad entries; every duplicated index is missing."""
    if not isinstance(raw, list):
        return []
    counts: Counter[int] = Counter()
    candidates = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        index = entry.get("option_index")
        if isinstance(index, float) and index.is_integer():
            index = int(index)
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        counts[index] += 1
        if index < 0 or (indexes is not None and index not in indexes):
            continue
        if entry.get("verdict") in ("approve", "decline"):
            candidates.append({"option_index": index, "verdict": entry["verdict"]})
    return [entry for entry in candidates if counts[entry["option_index"]] == 1]


def normalize_response(obj: Any, request: dict | None = None) -> Any:
    """Accept a usable shop action even when its board rulings need fallback.

    Do not synthesize approvals/declines: the mod knows whether the action landed,
    the original ask_on list, and the live turn store. It also records missing counts.
    """
    if not isinstance(obj, dict):
        return obj
    if request is not None and screen_for(request) == "shop":
        indexes = [o.get("index") for o in request.get("options") or [] if isinstance(o, dict)]
        return {**obj, "rulings": normalize_rulings(obj.get("rulings"), indexes)}
    return obj


def schema_for(request: dict) -> dict:
    """Specialize the shared schema before CLI top-level combinators are stripped.

    The response has no screen discriminator, and skip/revise_plan are shared
    with checkpoints. Required/absent rulings therefore depend on the request.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    screen = screen_for(request)
    allowed = SCREEN_ACTIONS.get(screen)
    if allowed is not None:
        data["properties"]["action"]["enum"] = list(allowed)
    if screen == "shop":
        data["required"].append("rulings")
        indexes = [
            o["index"]
            for o in request.get("options") or []
            if isinstance(o, dict) and isinstance(o.get("index"), int)
        ]
        rulings = data["properties"]["rulings"]
        # Let incomplete/duplicate rulings reach runtime normalization instead
        # of spending CLI turns repairing an otherwise usable action.
        if indexes:
            rulings["items"]["properties"]["option_index"]["enum"] = indexes
    else:
        del data["properties"]["rulings"]
    return data


def validate(obj: Any, request: dict | None = None, *, tolerate_rulings: bool = True) -> list[str]:
    """Return human-readable errors for ``obj``; an empty list means it is valid.

    With ``request``, the action must be one its ``screen`` applies (``SCREEN_ACTIONS``)
    and an ``option_index`` must be one of its ``options[].index``.
    Runtime tolerance matches the mod. ``tolerate_rulings=False`` checks the
    published contract instead, including complete and unique shop rulings.
    """
    if not isinstance(obj, dict):
        return [f"<root>: expected a JSON object, got {type(obj).__name__}"]
    try:
        normalized = normalize_response(obj, request) if tolerate_rulings else obj
        model = ShopDecision if request is not None and screen_for(request) == "shop" else Decision
        model.model_validate(normalized)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        ]
    if request is None:
        return []
    screen = screen_for(request)
    allowed = SCREEN_ACTIONS.get(screen)
    if allowed is not None and obj["action"] not in allowed:
        return [
            f"action: '{obj['action']}' is not allowed on the {screen} screen; use one of {allowed}"
        ]
    if screen != "shop" and "rulings" in obj:
        return [f"rulings: must be omitted on the {screen} screen"]
    indexes = [o.get("index") for o in request.get("options") or [] if isinstance(o, dict)]
    if "option_index" in obj and obj["option_index"] not in indexes:
        return [f"option_index: {obj['option_index']} is not an index in Options {indexes}"]
    if screen == "shop" and not tolerate_rulings:
        supplied = [r["option_index"] for r in obj["rulings"]]
        if len(supplied) != len(indexes) or set(supplied) != set(indexes):
            return [f"rulings: require exactly one verdict per Options index {indexes}"]
    return []
