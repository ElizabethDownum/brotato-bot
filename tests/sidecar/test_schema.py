import json

import pytest

from brotato_bot.sidecar import schema


def _buy(**overrides):
    obj = {
        "action": "buy",
        "option_index": 2,
        "confidence": 0.8,
        "rationale": "Strong scaling item for the plan.",
        "tags": ["economy"],
    }
    obj.update(overrides)
    return obj


def test_valid_buy():
    assert schema.validate(_buy()) == []
    decision = schema.Decision.model_validate(_buy())
    assert decision.action == "buy"
    assert decision.option_index == 2


def test_valid_skip_and_reroll_without_index():
    for action in ("skip", "reroll"):
        obj = _buy(action=action)
        del obj["option_index"]
        assert schema.validate(obj) == []


@pytest.mark.parametrize("action", ["buy", "lock", "pick"])
def test_buy_requires_option_index(action):
    obj = _buy(action=action)
    del obj["option_index"]
    errors = schema.validate(obj)
    assert errors
    assert any("option_index" in e for e in errors)


def test_rejects_negative_option_index():
    errors = schema.validate(_buy(option_index=-1))
    assert any("option_index" in e for e in errors)


def test_revise_requires_plan_patch():
    obj = _buy(action="revise_plan")
    del obj["option_index"]
    errors = schema.validate(obj)
    assert any("plan_patch" in e for e in errors)
    assert schema.validate({**obj, "plan_patch": {"focus": "ranged"}}) == []


def test_rejects_extra_fields():
    errors = schema.validate(_buy(extra="nope"))
    assert any("extra" in e for e in errors)


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_rejects_confidence_out_of_range(value):
    errors = schema.validate(_buy(confidence=value))
    assert any("confidence" in e for e in errors)


def test_rejects_unknown_action_and_long_rationale():
    assert any("action" in e for e in schema.validate(_buy(action="sell")))
    assert any("rationale" in e for e in schema.validate(_buy(rationale="x" * 301)))
    assert schema.validate(_buy(rationale="x" * 300)) == []


def test_rejects_missing_required():
    errors = schema.validate({"action": "skip"})
    for field in ("confidence", "rationale", "tags"):
        assert any(field in e for e in errors)


@pytest.mark.parametrize("value", [None, [], "buy", 3])
def test_non_dict_returns_error(value):
    errors = schema.validate(value)
    assert errors
    assert all(isinstance(e, str) for e in errors)


def test_schema_json_matches_model():
    data = json.loads(schema.SCHEMA_PATH.read_text(encoding="utf-8"))
    props = data["properties"]
    assert data["type"] == "object"
    assert data["additionalProperties"] is False
    assert data["required"] == ["action", "confidence", "rationale", "tags"]
    assert props["action"]["enum"] == ["buy", "reroll", "lock", "skip", "pick", "revise_plan"]
    assert set(props) == set(schema.Decision.model_fields)
    assert props["option_index"]["minimum"] == 0
    assert props["confidence"]["minimum"] == 0
    assert props["confidence"]["maximum"] == 1
    assert props["rationale"]["maxLength"] == 300
    assert props["tags"]["items"]["type"] == "string"

    conditionals = {}
    for rule in data["allOf"]:
        actions = rule["if"]["properties"]["action"]["enum"]
        for action in actions:
            conditionals[action] = rule["then"]["required"]
        assert rule["if"]["required"] == ["action"]
    assert conditionals == {
        "buy": ["option_index"],
        "lock": ["option_index"],
        "pick": ["option_index"],
        "revise_plan": ["plan_patch"],
    }


def test_rejects_explicit_null_and_coerced_types():
    assert any("option_index" in e for e in schema.validate(_buy(action="skip", option_index=None)))
    assert schema.validate(_buy(confidence=1)) == []
    assert any("confidence" in e for e in schema.validate(_buy(confidence="0.5")))
    assert any("option_index" in e for e in schema.validate(_buy(option_index=True)))
