"""Decision response schema shared with the mod and the Claude CLI.

``decision.schema.json`` is passed verbatim to ``claude -p --json-schema``; the
pydantic ``Decision`` model mirrors it and is the authority ``validate`` uses.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_PATH = Path(__file__).with_name("decision.schema.json")

Action = Literal["buy", "reroll", "lock", "skip", "pick", "revise_plan"]
NEEDS_OPTION_INDEX = frozenset({"buy", "lock", "pick"})


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Action
    option_index: int | None = Field(default=None, ge=0)
    plan_patch: dict[str, Any] | None = None
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


def validate(obj: Any) -> list[str]:
    """Return human-readable errors for ``obj``; an empty list means it is valid."""
    if not isinstance(obj, dict):
        return [f"<root>: expected a JSON object, got {type(obj).__name__}"]
    try:
        Decision.model_validate(obj)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        ]
    return []
