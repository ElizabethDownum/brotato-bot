"""Decision response schema shared with the mod and the Claude CLI.

``decision.schema.json`` is passed verbatim to ``claude -p --json-schema``; the
pydantic ``Decision`` model mirrors it and is the authority ``validate`` uses.
"""

from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator, with_config

SCHEMA_PATH = Path(__file__).with_name("decision.schema.json")

Action = Literal["buy", "reroll", "lock", "pass", "skip", "pick", "revise_plan"]
NEEDS_OPTION_INDEX = frozenset({"buy", "lock", "pass", "pick"})
# The actions each screen applies (base_shop.gd, upgrades_ui.gd, Checkpoint.wanted).
SCREEN_ACTIONS = {
    "shop": ("buy", "lock", "pass", "reroll", "skip", "revise_plan"),
    "levelup": ("pick",),
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


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Action
    option_index: int | None = Field(default=None, ge=0)
    plan_patch: PlanPatch | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=300)
    tags: list[str]

    @model_validator(mode="after")
    def _conditional_fields(self) -> "Decision":
        # Optional fields may be omitted but, as in the JSON Schema, not sent as null.
        for name in ("option_index", "plan_patch"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        if self.action in NEEDS_OPTION_INDEX and self.option_index is None:
            raise ValueError(f"option_index is required for action '{self.action}'")
        if self.action == "revise_plan" and self.plan_patch is None:
            raise ValueError("plan_patch is required for action 'revise_plan'")
        return self


def validate(obj: Any, request: dict | None = None) -> list[str]:
    """Return human-readable errors for ``obj``; an empty list means it is valid.

    With ``request``, the action must be one its ``screen`` applies (``SCREEN_ACTIONS``)
    and an ``option_index`` must be one of its ``options[].index``.
    """
    if not isinstance(obj, dict):
        return [f"<root>: expected a JSON object, got {type(obj).__name__}"]
    try:
        Decision.model_validate(obj)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        ]
    if request is None:
        return []
    screen = request.get("screen") or request.get("kind")
    allowed = SCREEN_ACTIONS.get(screen)
    if allowed is not None and obj["action"] not in allowed:
        return [
            f"action: '{obj['action']}' is not allowed on the {screen} screen; use one of {allowed}"
        ]
    indexes = [o.get("index") for o in request.get("options") or [] if isinstance(o, dict)]
    if "option_index" in obj and obj["option_index"] not in indexes:
        return [f"option_index: {obj['option_index']} is not an index in Options {indexes}"]
    return []
