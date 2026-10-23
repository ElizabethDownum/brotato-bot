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
        "stats": {"stat_harvesting": 10.0, "stat_ranged_damage": 8.0, "stat_speed": 2.0},
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
        "plan_id well-rounded-slow-v1",
    ]
    assert proposal.validate(text, SLOW, "2026-10-22-003.md") == []


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
    assert capsys.readouterr().out.strip() == f"{file} is already shaped for chal_slow"


def test_real_dataset_lists_the_speed_lowering_items():
    # The 2026-10-22 dataset: Esty's Couch alone reaches chal_slow's -20.
    dataset = REPO / "data" / "brotato.json"
    if not dataset.is_file():
        return
    shaped = shape.shape_plan(_plan(), shape.goal_for("chal_slow", SLOW), shape.load_items(dataset))
    bonus = shaped["plan"]["item_bonus"]
    assert bonus["item_estys_couch"] == 30.0 and bonus["item_statue"] == 15.0
    assert len([k for k in bonus if k != "item_bag"]) >= 15
