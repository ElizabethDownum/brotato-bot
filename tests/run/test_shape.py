import json
from pathlib import Path

from brotato_bot import cli
from brotato_bot.run import proposal, shape

REPO = Path(__file__).resolve().parents[2]
CHARACTER = "character_well_rounded"

ITEMS = [
    {
        "id": "item_statue",
        "effects": [{"key": "stat_attack_speed", "value": 40}, {"key": "stat_speed", "value": -10}],
    },
    {"id": "item_estys_couch", "effects": [{"key": "stat_speed", "value": -20}]},
    {"id": "item_bag", "effects": [{"key": "stat_speed", "value": -1}]},
    {"id": "item_fin", "effects": [{"key": "stat_speed", "value": 10}]},
    {"id": "item_cursed_thing", "effects": [{"key": "stat_curse", "value": 5}]},
    {"id": "item_plain", "effects": [{"key": "stat_max_hp", "value": 3}]},
]


def _state(target, **progress):
    info = {"requires_character": None, "stat": "", "number": 0, "value": 0}
    info.update(progress)
    return {
        "characters": {CHARACTER: {"unlocked": True, "unlocked_by": None}},
        "done": [],
        "open": [target],
        "blocked": [],
        "progress": {target: info},
    }


SLOW = _state("chal_slow", stat="stat_speed", value=-20)
UNCORRUPTED = _state("chal_uncorrupted", stat="stat_curse", value=0)
DIFFICULTY_2 = _state("chal_difficulty_2", number=2, value=2)
PLAIN = _state("chal_gatherer_1", value=5)


def _plan(plan_id="well-rounded-v1", **body):
    plan = {
        "weapon_type": "ranged",
        "weapon_set": "",
        "stats": {
            "stat_harvesting": 10.0,
            "stat_ranged_damage": 8.0,
            "stat_speed": 2.0,
            "stat_max_hp": 5.0,
            "stat_armor": 3.0,
            "stat_luck": 1.0,
        },
        "item_bonus": {"item_bag": 1.0},
        "ban_items": [],
    }
    plan.update(body)
    return {"plan_id": plan_id, "character_id": CHARACTER, "plan": plan}


def _proposal(target, danger=0, plan=None):
    plan = plan or _plan()
    return (
        "# Proposal 3\n\n## Target\nx\n\n## Next run\n"
        f"- character: {CHARACTER}\n- danger: {danger}\n- target: {target}\n\n"
        "## Plan\n```json\n" + json.dumps(plan, indent=2) + "\n```\n\n"
        "## Why\nx\n\n## Risk\nx\n\n## Stagnation check\nfresh: no runs on any target\n"
    )


def test_goal_for_reads_stat_value_and_difficulty():
    g = shape.goal_for("chal_slow", SLOW)
    assert (g.stat, g.value, g.sign, g.danger) == ("stat_speed", -20, -1, None)
    g = shape.goal_for("chal_difficulty_2", DIFFICULTY_2)
    assert (g.stat, g.danger) == ("", 2)
    assert shape.goal_for("chal_gatherer_1", PLAIN) is None
    assert shape.goal_for(None, PLAIN) is None


def test_shape_plan_makes_the_goal_stat_dominant_with_the_goal_sign():
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_slow", SLOW), ITEMS)
    stats = shaped["plan"]["stats"]
    assert stats["stat_speed"] == -14.0  # largest other weight 10 + margin 4, negative
    assert stats["stat_harvesting"] == 10.0


def test_shape_plan_adds_item_bonuses_for_items_that_move_the_stat_the_right_way():
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_slow", SLOW), ITEMS)
    bonus = shaped["plan"]["item_bonus"]
    assert bonus["item_statue"] == 15.0
    assert bonus["item_estys_couch"] == 30.0  # 1.5 * 20 is exactly the cap
    assert bonus["item_bag"] == 1.5  # raised from the row's 1.0
    assert "item_fin" not in bonus and "item_plain" not in bonus
    assert shaped["plan"]["ban_items"] == []


def test_shape_plan_bans_items_that_break_a_keep_at_zero_goal():
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_uncorrupted", UNCORRUPTED), ITEMS)
    assert shaped["plan"]["ban_items"] == ["item_cursed_thing"]
    assert shaped["plan"]["stats"]["stat_curse"] == -14.0


def test_shape_plan_adds_the_goal_to_the_family_and_keeps_the_version():
    goal = shape.goal_for("chal_slow", SLOW)
    assert (
        shape.shape_plan(_plan("well-rounded-v3"), goal, ITEMS)["plan_id"] == "well-rounded-slow-v3"
    )
    assert (
        shape.shape_plan(_plan("well-rounded-slow-v1"), goal, ITEMS)["plan_id"]
        == "well-rounded-slow-v1"
    )


def test_shape_plan_does_not_create_ban_items_for_a_nonzero_goal():
    plan = _plan()
    del plan["plan"]["ban_items"]
    shaped = shape.shape_plan(plan, shape.goal_for("chal_slow", SLOW), ITEMS)
    assert "ban_items" not in shaped["plan"]
    text, changes = shape.shape_markdown(
        _proposal("chal_slow", plan=plan), shape.goal_for("chal_slow", SLOW), ITEMS
    )
    assert not any("banned" in c for c in changes)
    assert "ban_items" not in proposal.extract_plan(text)["plan"]


def test_shape_plan_sums_an_items_effects_on_the_goal_stat():
    items = [
        {
            "id": "item_two",
            "effects": [{"key": "stat_speed", "value": -4}, {"key": "stat_speed", "value": -6}],
        }
    ]
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_slow", SLOW), items)
    assert shaped["plan"]["item_bonus"]["item_two"] == 15.0


def test_goal_for_keeps_a_float_value():
    state = _state("chal_slow", stat="stat_speed", value=-20.0)
    g = shape.goal_for("chal_slow", state)
    assert (g.value, g.sign) == (-20.0, -1)
    shaped = shape.shape_plan(_plan(), g, ITEMS)
    assert shaped["plan"]["stats"]["stat_speed"] == -14.0
    text, changes = shape.shape_markdown(_proposal("chal_slow"), g, ITEMS)
    assert changes[0] == "stat_speed weight -14 (goal -20), 2 item bonuses"
    assert proposal.validate(text, state, "2026-10-22-003.md") == []


def test_validate_requires_the_full_stats_row():
    plan = _plan()
    plan["plan"]["stats"] = {"stat_harvesting": 10.0, "stat_speed": -14.0, "stat_luck": 1.0}
    errors = proposal.validate(_proposal("chal_slow", plan=plan), SLOW, "2026-10-22-003.md")
    expected = (
        "## Plan: stats has only 2 weights besides stat_speed; "
        "copy the character's full row before shaping"
    )
    assert errors == [expected]
    plan["plan"]["stats"].update(stat_max_hp=5.0, stat_armor=3.0)
    assert proposal.validate(_proposal("chal_slow", plan=plan), SLOW, "2026-10-22-003.md") == []


def test_shape_plan_leaves_the_input_untouched():
    plan = _plan()
    shape.shape_plan(plan, shape.goal_for("chal_slow", SLOW), ITEMS)
    assert plan == _plan()


def test_shape_markdown_rewrites_the_plan_block_and_reports_changes():
    text, changes = shape.shape_markdown(
        _proposal("chal_slow"), shape.goal_for("chal_slow", SLOW), ITEMS
    )
    plan = proposal.extract_plan(text)
    assert plan["plan"]["stats"]["stat_speed"] == -14.0
    assert plan["plan_id"] == "well-rounded-slow-v1"
    assert changes == [
        "stat_speed weight -14 (goal -20), 2 item bonuses",
        "min_buy 6",
        "plan_id well-rounded-slow-v1",
    ]
    assert proposal.validate(text, SLOW, "2026-10-22-003.md") == []


def test_shape_plan_raises_a_low_min_buy_under_a_stat_goal():
    goal = shape.goal_for("chal_slow", SLOW)
    assert shape.shape_plan(_plan(min_buy=2.0), goal, ITEMS)["plan"]["min_buy"] == 6.0
    assert shape.shape_plan(_plan(), goal, ITEMS)["plan"]["min_buy"] == 6.0


def test_shape_plan_keeps_a_higher_min_buy_and_is_idempotent():
    goal = shape.goal_for("chal_slow", SLOW)
    assert shape.shape_plan(_plan(min_buy=6.0), goal, ITEMS)["plan"]["min_buy"] == 6.0
    once = shape.shape_plan(_plan(), goal, ITEMS)
    assert shape.shape_plan(once, goal, ITEMS) == once


def test_shape_markdown_reports_min_buy_only_when_it_changed():
    goal = shape.goal_for("chal_slow", SLOW)
    _, low = shape.shape_markdown(_proposal("chal_slow", plan=_plan(min_buy=2.0)), goal, ITEMS)
    assert "min_buy 6" in low
    _, high = shape.shape_markdown(_proposal("chal_slow", plan=_plan(min_buy=6.0)), goal, ITEMS)
    assert not any(c.startswith("min_buy") for c in high)


def test_shape_markdown_raises_danger_for_a_difficulty_target():
    text, changes = shape.shape_markdown(
        _proposal("chal_difficulty_2", danger=0),
        shape.goal_for("chal_difficulty_2", DIFFICULTY_2),
        ITEMS,
    )
    assert proposal.next_run(text)["danger"] == 2
    assert changes == ["danger 2"]
    assert proposal.extract_plan(text) == _plan()
    again, changes = shape.shape_markdown(
        text, shape.goal_for("chal_difficulty_2", DIFFICULTY_2), ITEMS
    )
    assert again == text and changes == []


def test_shape_markdown_is_idempotent_and_a_noop_without_a_goal():
    text, _ = shape.shape_markdown(_proposal("chal_slow"), shape.goal_for("chal_slow", SLOW), ITEMS)
    again, changes = shape.shape_markdown(text, shape.goal_for("chal_slow", SLOW), ITEMS)
    assert again == text and changes == []
    assert shape.shape_markdown(_proposal("chal_gatherer_1"), None, ITEMS) == (
        _proposal("chal_gatherer_1"),
        [],
    )


def test_validate_rejects_an_unshaped_plan_for_a_stat_target():
    errors = proposal.validate(_proposal("chal_slow"), SLOW, "2026-10-22-003.md")
    assert errors == [
        "## Plan: not shaped for chal_slow: run proposal shape FILE (goal stat_speed -20)"
    ]


def test_validate_rejects_a_goal_weight_that_is_not_dominant():
    plan = _plan()
    plan["plan"]["stats"]["stat_speed"] = -5.0
    errors = proposal.validate(_proposal("chal_slow", plan=plan), SLOW, "2026-10-22-003.md")
    assert errors == [
        "## Plan: stat_speed weight -5 is not the plan's largest: run proposal shape FILE (goal stat_speed -20)"
    ]


def test_validate_rejects_too_low_a_danger_for_a_difficulty_target():
    errors = proposal.validate(
        _proposal("chal_difficulty_2", danger=1), DIFFICULTY_2, "2026-10-22-003.md"
    )
    assert errors == ["## Next run: target chal_difficulty_2 needs danger 2, not 1"]
    assert (
        proposal.validate(
            _proposal("chal_difficulty_2", danger=2), DIFFICULTY_2, "2026-10-22-003.md"
        )
        == []
    )


def test_cli_shape_rewrites_the_file_and_prints_the_changes(tmp_path, monkeypatch, capsys):
    from brotato_bot import paths

    data = tmp_path / "data"
    data.mkdir()
    (data / "unlock_state.json").write_text(json.dumps({"profile": 1, **SLOW}), encoding="utf-8")
    (data / "brotato.json").write_text(json.dumps({"items": ITEMS}), encoding="utf-8")
    real = paths.load()
    monkeypatch.setattr(
        paths, "load", lambda: real.__class__(**{**real.__dict__, "data_dir": data})
    )
    file = tmp_path / "2026-10-22-003.md"
    file.write_text(_proposal("chal_slow"), encoding="utf-8")
    assert cli.main(["proposal", "shape", str(file)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"shaped {file} for chal_slow: stat_speed weight -14 (goal -20)")
    assert (
        proposal.extract_plan(file.read_text(encoding="utf-8"))["plan_id"] == "well-rounded-slow-v1"
    )
    assert cli.main(["proposal", "shape", str(file)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"{file} is already shaped for chal_slow"


def test_real_dataset_lists_the_speed_lowering_items():
    # The 2026-10-22 dataset: Esty's Couch alone reaches chal_slow's -20.
    dataset = REPO / "data" / "brotato.json"
    if not dataset.is_file():
        return
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_slow", SLOW), shape.load_items(dataset))
    bonus = shaped["plan"]["item_bonus"]
    assert bonus["item_estys_couch"] == 30.0 and bonus["item_statue"] == 15.0
    assert len([k for k in bonus if k != "item_bag"]) >= 15


GOAL_DATASET = {
    "items": [
        {
            "id": "item_slug",
            "tier": 1,
            "value": 20,
            "effects": [{"key": "stat_speed", "value": -5}],
        },
        {
            "id": "item_couch",
            "tier": 3,
            "value": 90,
            "effects": [{"key": "stat_speed", "value": -20}],
        },
        {"id": "item_fin", "tier": 1, "value": 10, "effects": [{"key": "stat_speed", "value": 10}]},
        {
            "id": "item_plain",
            "tier": 1,
            "value": 5,
            "effects": [{"key": "stat_max_hp", "value": 3}],
        },
    ],
    "weapons": [
        {"id": "weapon_mace_1", "weapon_type": "melee", "sets": ["Blunt"]},
        {"id": "weapon_club_1", "weapon_type": "melee", "sets": ["Blunt", "Primitive"]},
        {"id": "weapon_gun_1", "weapon_type": "ranged", "sets": ["Gun"]},
    ],
    "sets": [
        {
            "id": "set_blunt",
            "name": "Blunt",
            "display_name": "Blunt",
            "bonuses": [
                {"count": 2, "effect": {"key": "stat_speed", "value": -2}},
                {
                    "count": 6,
                    "effect": {"key": "stat_armor", "value": 3},
                    "effects": [
                        {"key": "stat_armor", "value": 3},
                        {"key": "stat_max_hp", "value": 6},
                        {"key": "stat_speed", "value": -10},
                    ],
                },
            ],
        },
        {
            "id": "set_gun",
            "name": "Gun",
            "display_name": "Gun",
            "bonuses": [{"count": 2, "effect": {"key": "stat_ranged_damage", "value": 1}}],
        },
    ],
}


def test_goal_data_lists_items_and_set_bonuses_that_move_the_stat():
    goal = shape.goal_for("chal_slow", SLOW)
    assert shape.goal_data(goal, GOAL_DATASET) == {
        "items": [
            {"id": "item_couch", "value": -20.0, "tier": 3, "price": 90},
            {"id": "item_slug", "value": -5.0, "tier": 1, "price": 20},
        ],
        "sets": [
            {
                "id": "set_blunt",
                "name": "Blunt",
                "weapon_types": ["melee"],
                "by_count": {2: -2.0, 6: -10.0},
            }
        ],
    }
    assert shape.goal_data(
        shape.goal_for("chal_gatherer_1", PLAIN) or shape.Goal("x"), GOAL_DATASET
    ) == {
        "items": [],
        "sets": [],
    }


def test_brief_lines_text():
    goal = shape.goal_for("chal_slow", SLOW)
    assert shape.brief_lines(goal, shape.goal_data(goal, GOAL_DATASET)) == [
        "Goal data for chal_slow: lower stat_speed to -20.",
        "item_couch -20 (tier 3, price 90), item_slug -5 (tier 1, price 20)",
        "set_blunt (melee): 2 weapons -2, 6 weapons -10",
    ]
    empty = {"items": [], "sets": []}
    assert shape.brief_lines(goal, empty)[1:] == [
        "No item in the dataset lowers stat_speed.",
        "No weapon set in the dataset lowers stat_speed.",
    ]
    assert shape.brief_lines(shape.Goal("x"), empty) == []


def test_objective_includes_the_goal_data_only_with_a_dataset():
    from brotato_bot.sidecar import prompt

    state = {"target_challenge": "chal_slow"}
    without = prompt._objective(state, {}, SLOW, "shop")
    assert not any(line.startswith("Goal data") for line in without)
    with_data = prompt._objective(state, {}, SLOW, "shop", dataset=GOAL_DATASET)
    assert with_data[-1] == without[-1]
    assert with_data[-4] == "Goal data for chal_slow: lower stat_speed to -20."
    assert with_data[-3].startswith("item_couch -20")
    assert with_data[-2] == "set_blunt (melee): 2 weapons -2, 6 weapons -10"
    assert len(with_data) == len(without) + 3
    checkpoint = prompt._objective(state, {}, SLOW, "checkpoint", dataset=GOAL_DATASET)
    assert checkpoint == prompt._objective(state, {}, SLOW, "checkpoint")


def test_cli_shape_prints_the_goal_data_after_the_shaped_line(tmp_path, monkeypatch, capsys):
    from brotato_bot import paths

    data = tmp_path / "data"
    data.mkdir()
    (data / "unlock_state.json").write_text(json.dumps({"profile": 1, **SLOW}), encoding="utf-8")
    (data / "brotato.json").write_text(json.dumps(GOAL_DATASET), encoding="utf-8")
    real = paths.load()
    monkeypatch.setattr(
        paths, "load", lambda: real.__class__(**{**real.__dict__, "data_dir": data})
    )
    file = tmp_path / "2026-10-22-003.md"
    file.write_text(_proposal("chal_slow"), encoding="utf-8")
    assert cli.main(["proposal", "shape", str(file)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(f"shaped {file} for chal_slow")
    assert lines[1:] == [
        "Goal data for chal_slow: lower stat_speed to -20.",
        "item_couch -20 (tier 3, price 90), item_slug -5 (tier 1, price 20)",
        "set_blunt (melee): 2 weapons -2, 6 weapons -10",
    ]


def _blunt_dataset(six=-10.0, character=None):
    set_blunt = {
        "id": "set_blunt",
        "name": "Blunt",
        "bonuses": [
            {"count": 2, "effects": [{"key": "stat_speed", "value": -2}]},
            {"count": 6, "effects": [{"key": "stat_speed", "value": six}]},
        ],
    }
    return {
        "items": ITEMS,
        "sets": [set_blunt],
        "characters": [character or {"id": CHARACTER, "flat_bonuses": []}],
    }


def test_shape_prefers_a_set_that_covers_a_quarter_of_the_need():
    goal = shape.goal_for("chal_slow", SLOW)
    shaped = shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset())
    body = shaped["plan"]
    assert body["prefer_sets"] == {"set_blunt": 15.0}  # 10 goal units * 1.5 per unit
    assert body["weapon_type"] == "any"
    assert body["weapon_set"] == ""  # the hard gate stays unset
    # exactly at the threshold: need 20, 25% is 5
    at = shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset(six=-5.0))
    assert at["plan"]["prefer_sets"] == {"set_blunt": 7.5}


def test_shape_does_not_prefer_a_set_below_a_quarter_of_the_need():
    goal = shape.goal_for("chal_slow", SLOW)
    shaped = shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset(six=-4.0))
    assert "prefer_sets" not in shaped["plan"]
    assert shaped["plan"]["weapon_type"] == "ranged"
    assert "prefer_sets" not in shape.shape_plan(_plan(), goal, ITEMS)["plan"]  # no dataset


def test_the_characters_start_lowers_the_need_and_so_the_threshold():
    goal = shape.goal_for("chal_slow", SLOW)
    old = {"id": CHARACTER, "flat_bonuses": [{"stat": "stat_speed", "value": -10}]}
    # need 10, threshold 2.5: a -4 set now qualifies; with a +5 start (need 25) it does not
    assert (
        "prefer_sets" in shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset(-4.0, old))["plan"]
    )
    slow_start = {"id": CHARACTER, "flat_bonuses": [{"stat": "stat_speed", "value": 5}]}
    assert (
        "prefer_sets"
        not in shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset(-6.0, slow_start))["plan"]
    )


def test_prefer_sets_bonus_is_capped():
    goal = shape.goal_for("chal_slow", SLOW)
    shaped = shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset(six=-30.0))
    assert shaped["plan"]["prefer_sets"] == {"set_blunt": shape.ITEM_BONUS_CAP}


def test_chunky_cannot_prefer_sets_for_its_vetoed_speed_goal():
    goal = shape.goal_for("chal_slow", SLOW)
    chunky = {
        "id": "character_chunky",
        "gain_modifiers": [{"stat": "stat_speed", "pct": -100}],
    }
    dataset = _blunt_dataset(character=chunky)
    assert shape.preferred_sets(goal, dataset, chunky) == {}
    plan = {**_plan(), "character_id": chunky["id"]}
    shaped = shape.shape_plan(plan, goal, ITEMS, dataset)
    assert "prefer_sets" not in shaped["plan"]
    assert shaped["plan"]["weapon_type"] == "ranged"


def test_shape_markdown_reports_the_set_and_is_idempotent():
    goal = shape.goal_for("chal_slow", SLOW)
    dataset = _blunt_dataset()
    text, changes = shape.shape_markdown(_proposal("chal_slow"), goal, ITEMS, dataset)
    assert "prefer_sets set_blunt 15" in changes and "weapon_type any" in changes
    plan = proposal.extract_plan(text)["plan"]
    assert plan["prefer_sets"] == {"set_blunt": 15.0} and plan["weapon_type"] == "any"
    again, changes = shape.shape_markdown(text, goal, ITEMS, dataset)
    assert changes == [] and again == text


def test_goal_errors_accepts_prefer_sets_and_rejects_a_bad_one():
    goal = shape.goal_for("chal_slow", SLOW)
    run = {"target": "chal_slow", "danger": 0}
    shaped = shape.shape_plan(_plan(), goal, ITEMS, _blunt_dataset())
    assert shape.goal_errors(shaped, run, SLOW) == []
    shaped["plan"]["prefer_sets"] = {"set_blunt": 99}
    assert any("prefer_sets" in e for e in shape.goal_errors(shaped, run, SLOW))
