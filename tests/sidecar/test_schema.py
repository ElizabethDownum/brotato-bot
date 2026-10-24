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
    assert decision.rulings is None


@pytest.mark.parametrize("action", ["buy", "lock", "pass", "reroll", "skip", "revise_plan"])
def test_shop_rulings_accompany_any_action_and_do_not_invalidate_it(action):
    obj = _buy(
        action=action,
        option_index=0,
        rulings=[
            {"option_index": 0, "verdict": "approve"},
            {"option_index": 1, "verdict": "decline"},
        ],
    )
    if action == "revise_plan":
        obj["plan_patch"] = {}
    assert schema.validate(obj, SHOP) == []
    assert schema.ShopDecision.model_validate(obj).rulings[1].verdict == "decline"


@pytest.mark.parametrize("value", [None, "1", 1, {}, [True], [None], ["1"], [1.5], [[]]])
def test_rulings_runtime_fallback_tolerates_non_array_or_malformed_entries(value):
    obj = _buy(option_index=0, rulings=value)
    assert schema.validate(obj, SHOP) == []
    assert schema.normalize_response(obj, SHOP)["rulings"] == []
    with pytest.raises(ValueError):
        schema.ShopDecision.model_validate(obj)


def test_rulings_partial_duplicate_bad_range_and_contradiction_normalization():
    obj = _buy(
        option_index=0,
        rulings=[
            {"option_index": 0.0, "verdict": "decline"},
            {"option_index": 1, "verdict": "approve"},
            {"option_index": 1, "verdict": "bad"},
            {"option_index": -1, "verdict": "approve"},
            {"option_index": 99, "verdict": "decline"},
            {"option_index": True, "verdict": "approve"},
        ],
    )
    assert schema.validate(obj, SHOP) == []
    normalized = schema.normalize_response(obj, SHOP)
    assert normalized["rulings"] == [{"option_index": 0, "verdict": "decline"}]
    assert normalized["action"] == "buy"  # the mod overrides after a successful buy
    assert schema.normalize_response(_buy(option_index=0), SHOP)["rulings"] == []


def test_strict_shop_model_requires_rulings_and_other_screens_forbid_them():
    with pytest.raises(ValueError, match="rulings"):
        schema.ShopDecision.model_validate(_buy())
    assert schema.validate(_buy(action="pick", rulings=[]), LEVELUP)[0].startswith("rulings")
    assert schema.validate({**_revise({}), "rulings": []}, CHECKPOINT)[0].startswith("rulings")


def test_published_contract_requires_complete_unique_in_range_rulings():
    obj = _buy(
        option_index=0,
        rulings=[
            {"option_index": 0, "verdict": "decline"},
            {"option_index": 1, "verdict": "approve"},
        ],
    )
    # Buy/pass contradictions are tolerated even by the strict shape contract.
    assert schema.validate(obj, SHOP, tolerate_rulings=False) == []
    for bad in (
        [],
        obj["rulings"][:1],
        [obj["rulings"][0]] * 2,
        [{"option_index": 99, "verdict": "decline"}],
        [{"option_index": 0, "verdict": "bad"}],
    ):
        assert schema.validate({**obj, "rulings": bad}, SHOP, tolerate_rulings=False)
        assert schema.validate({**obj, "rulings": bad}, SHOP) == []
    missing = {k: v for k, v in obj.items() if k != "rulings"}
    assert schema.validate(missing, SHOP, tolerate_rulings=False)[0].startswith("rulings")
    assert schema.validate(missing, SHOP) == []


@pytest.mark.parametrize("kind,screen", [("shop", "shop"), ("pivot", "shop"), ("pivot", None)])
def test_shop_structured_schema_leaves_coverage_to_runtime(kind, screen):
    request = {**SHOP, "kind": kind}
    if screen:
        request["screen"] = screen
    else:
        request.pop("screen")
    data = schema.schema_for(request)
    assert "rulings" in data["required"]
    field = data["properties"]["rulings"]
    assert not {"minItems", "maxItems", "uniqueItems", "allOf", "contains"} & field.keys()
    assert field["items"]["properties"]["option_index"]["enum"] == [0, 1]
    assert data["properties"]["action"]["enum"] == list(schema.SCREEN_ACTIONS["shop"])


def test_empty_shop_structured_schema_has_no_invalid_empty_enum():
    data = schema.schema_for({"screen": "shop", "options": []})
    assert "rulings" in data["required"]
    assert "enum" not in data["properties"]["rulings"]["items"]["properties"]["option_index"]


@pytest.mark.parametrize("screen", ["crate", "levelup", "checkpoint"])
def test_nonshop_structured_schema_has_no_rulings_even_for_pivots(screen):
    data = schema.schema_for({"screen": screen, "kind": "pivot", "options": []})
    assert "rulings" not in data["properties"]
    assert "rulings" not in data["required"]


def test_valid_skip_and_reroll_without_index():
    for action in ("skip", "reroll"):
        obj = _buy(action=action)
        del obj["option_index"]
        assert schema.validate(obj) == []


@pytest.mark.parametrize("action", ["buy", "lock", "pass", "pick"])
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
    assert schema.validate({**obj, "plan_patch": {"weapon_type": "ranged"}}) == []


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
    assert props["action"]["enum"] == [
        "buy",
        "reroll",
        "lock",
        "pass",
        "skip",
        "pick",
        "take",
        "recycle",
        "revise_plan",
    ]
    assert set(props) == set(schema.Decision.model_fields)
    assert props["option_index"]["minimum"] == 0
    ruling = props["rulings"]["items"]
    assert ruling["required"] == ["option_index", "verdict"]
    assert ruling["additionalProperties"] is False
    assert ruling["properties"]["verdict"]["enum"] == ["approve", "decline"]
    assert props["confidence"]["minimum"] == 0
    assert props["confidence"]["maximum"] == 1
    assert props["rationale"]["maxLength"] == 300
    assert props["tags"]["items"]["type"] == "string"

    conditionals = {}
    for rule in data["allOf"]:
        actions = rule["if"]["properties"]["action"]["enum"]
        if rule["then"] in ({"required": ["rulings"]}, {"not": {"required": ["rulings"]}}):
            continue
        if actions == ["take", "recycle"]:
            assert rule["then"] == {"not": {"required": ["option_index"]}}
            continue
        for action in actions:
            conditionals[action] = rule["then"]["required"]
        assert rule["if"]["required"] == ["action"]
    assert conditionals == {
        "buy": ["option_index"],
        "lock": ["option_index"],
        "pass": ["option_index"],
        "pick": ["option_index"],
        "revise_plan": ["plan_patch"],
    }


def test_rejects_explicit_null_and_coerced_types():
    assert any("option_index" in e for e in schema.validate(_buy(action="skip", option_index=None)))
    assert schema.validate(_buy(confidence=1)) == []
    assert any("confidence" in e for e in schema.validate(_buy(confidence="0.5")))
    assert any("option_index" in e for e in schema.validate(_buy(option_index=True)))


def _revise(patch):
    return {
        "action": "revise_plan",
        "plan_patch": patch,
        "confidence": 0.6,
        "rationale": "r",
        "tags": [],
    }


@pytest.mark.parametrize("policy", ["auto", "seek", "preserve"])
@pytest.mark.parametrize("drop_pull", ["linear", "target"])
def test_plan_patch_accepts_steering(policy, drop_pull):
    steering = {
        "tree_policy": policy,
        "drop_pull": drop_pull,
        "tree_value": 4,
        "sweep": 1.5,
        "sweep_radius": 420,
        "gold_value": 0.8,
        "stand_continuity": -0.2,
    }
    assert schema.validate(_revise({"steering": steering})) == []
    assert schema.validate(_revise({"steering": {}})) == []


@pytest.mark.parametrize(
    "key", ["tree_value", "sweep", "sweep_radius", "gold_value", "stand_continuity"]
)
@pytest.mark.parametrize("value", [True, "1.5", None, [], {}])
def test_plan_patch_rejects_wrong_steering_number(key, value):
    assert schema.validate(_revise({"steering": {key: value}}))


@pytest.mark.parametrize(
    "steering",
    [None, [], "seek", {"unknown": 1}, {"tree_policy": "avoid"}, {"tree_policy": True}],
)
def test_plan_patch_rejects_bad_steering(steering):
    assert schema.validate(_revise({"steering": steering}))


def test_json_schema_steering_matches_model():
    data = json.loads(schema.SCHEMA_PATH.read_text(encoding="utf-8"))
    steering = data["properties"]["plan_patch"]["properties"]["steering"]
    assert steering["type"] == "object"
    assert steering["additionalProperties"] is False
    assert set(steering["properties"]) == set(schema.Steering.__annotations__)
    assert steering["properties"]["tree_policy"] == {
        "type": "string",
        "enum": ["auto", "seek", "preserve"],
    }
    assert steering["properties"]["drop_pull"] == {
        "type": "string",
        "enum": ["linear", "target"],
    }
    assert all(
        value == {"type": "number"}
        for key, value in steering["properties"].items()
        if key not in {"tree_policy", "drop_pull"}
    )


@pytest.mark.parametrize("value", ["auto", 1, True, None, [], {}])
def test_plan_patch_rejects_invalid_drop_pull(value):
    assert schema.validate(_revise({"steering": {"drop_pull": value}}))


def test_plan_patch_accepts_the_plan_keys_the_mod_reads():
    patch = {
        "weapon_type": "melee",
        "stats": {"stat_armor": 4, "stat_dodge": 2.5},
        "item_bonus": {"item_scar": 6.0},
        "phase_boost": {"until_wave": 7, "stats": {"stat_max_hp": 2.2}},
        "harvest_cap": 40,
        "max_weapons": 6,
        "reroll_keep": 5,
        "max_rerolls": 10,
        "gold_floor": 30,
        "min_buy": 2.0,
        "prefer_weapons": ["weapon_taser"],
        "ban_items": ["item_medical_gun"],
        "deprioritize_weapons": [],
        "ask_on": ["item_scar"],
        "weapon_set": "set_elemental",
        "unique_weapons": True,
        "stack_combine": False,
        "hitrate_pref": True,
        "spend_surplus": False,
    }
    assert schema.validate(_revise(patch)) == []
    assert schema.validate(_revise({"phase_boost": {}})) == []


@pytest.mark.parametrize(
    "patch",
    [
        {"focus": "ranged"},
        {"min_buy": "2"},
        {"max_rerolls": 2.5},
        {"max_rerolls": True},
        {"ask_on": "item_scar"},
        {"ask_on": [3]},
        {"stats": {"stat_armor": "high"}},
        {"stats": [1, 2]},
        {"item_bonus": {"item_scar": None}},
        {"weapon_type": "magic"},
        {"phase_boost": {"until_wave": 7, "stats": {"stat_max_hp": "x"}}},
        {"phase_boost": {"wave": 7}},
        {"unique_weapons": "yes"},
        {"max_rerolls": None},
    ],
)
def test_plan_patch_rejects_unknown_keys_and_wrong_types(patch):
    errors = schema.validate(_revise(patch))
    assert errors and all(e.startswith("plan_patch") for e in errors), errors


def test_schema_json_plan_patch_mirrors_the_whitelist():
    data = json.loads(schema.SCHEMA_PATH.read_text(encoding="utf-8"))
    patch = data["properties"]["plan_patch"]
    assert patch["additionalProperties"] is False
    assert set(patch["properties"]) == set(schema.PlanPatch.__annotations__)
    kinds = {k: v.get("type") for k, v in patch["properties"].items()}
    assert {k for k, t in kinds.items() if t == "integer"} == set(schema.INT_PLAN_KEYS)
    assert patch["properties"]["ask_on"]["items"]["type"] == "string"
    assert patch["properties"]["stats"]["additionalProperties"]["type"] == "number"


SHOP = {"screen": "shop", "options": [{"index": 0}, {"index": 1}]}
LEVELUP = {"screen": "levelup", "options": [{"index": 0}, {"index": 1}, {"index": 2}]}
CHECKPOINT = {"screen": "checkpoint", "options": []}


@pytest.mark.parametrize(
    ("request_", "obj"),
    [
        (SHOP, _buy(option_index=1)),
        (SHOP, _buy(action="pass", option_index=1)),
        (SHOP, _buy(action="reroll", option_index=0)),
        (SHOP, _revise({"min_buy": 3.0})),
        (LEVELUP, _buy(action="pick", option_index=2)),
        (CHECKPOINT, _revise({"min_buy": 3.0})),
        (CHECKPOINT, {k: v for k, v in _buy(action="skip").items() if k != "option_index"}),
    ],
)
def test_validate_accepts_actions_legal_for_the_screen(request_, obj):
    assert schema.validate(obj, request_) == []


@pytest.mark.parametrize(
    ("request_", "obj", "field"),
    [
        (LEVELUP, _revise({"min_buy": 3.0}), "action"),
        (LEVELUP, {k: v for k, v in _buy(action="skip").items() if k != "option_index"}, "action"),
        (SHOP, _buy(action="pick", option_index=0), "action"),
        (LEVELUP, _buy(action="pass", option_index=0), "action"),
        (CHECKPOINT, _buy(action="pass", option_index=0), "action"),
        (SHOP, _buy(action="pass", option_index=2), "option_index"),
        (SHOP, _buy(action="pass", option_index=-1), "option_index"),
        (SHOP, _buy(action="pass", option_index=None), "<root>"),
        (SHOP, _buy(action="pass", option_index=True), "option_index"),
        (SHOP, _buy(action="pass", option_index=1.5), "option_index"),
        (CHECKPOINT, _buy(option_index=0), "action"),
        (SHOP, _buy(option_index=2), "option_index"),
        (LEVELUP, _buy(action="pick", option_index=3), "option_index"),
    ],
)
def test_validate_rejects_illegal_action_or_index_for_the_request(request_, obj, field):
    errors = schema.validate(obj, request_)
    assert errors and all(e.startswith(field) for e in errors), errors


@pytest.mark.parametrize("action", ["take", "recycle"])
def test_crate_action_has_no_index_and_is_only_legal_on_crates(action):
    obj = {"action": action, "confidence": 0.8, "rationale": "survival", "tags": []}
    assert schema.validate(obj, {"screen": "crate", "options": [{"index": 0}]}) == []
    assert schema.validate(dict(obj, option_index=0))
    for request_ in (SHOP, LEVELUP, CHECKPOINT):
        assert "not allowed" in schema.validate(obj, request_)[0]
    for illegal in ("buy", "pick", "skip", "pass", "lock", "reroll", "revise_plan"):
        wrong = dict(_buy(action=illegal), plan_patch={})
        assert schema.validate(wrong, {"screen": "crate", "options": [{"index": 0}]})
