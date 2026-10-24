import json

import pytest

from brotato_bot import cli, paths
from brotato_bot.run import fit, shape

BUILD_PLANS = """
const PLANS := {
	"character_old": {
		"weapon_type": "ranged",
		"stats": {
			"stat_ranged_damage": 8.0,
			"stat_harvesting": 7.0,
		},
		"max_weapons": 6,
	},
	"character_plain": {
		"weapon_type": "ranged",
		"stats": {"stat_ranged_damage": 8.0},
	},
}
"""


def _char(cid, flat=(), gain=(), banned=(), pool=()):
    return {
        "id": cid,
        "flat_bonuses": [{"stat": s, "value": v} for s, v in flat],
        "gain_modifiers": [{"stat": s, "pct": p} for s, p in gain],
        "banned_item_groups": list(banned),
        "starting_weapon_pool": list(pool),
        "dlc": None,
    }


DATASET = {
    "items": [
        {"id": "item_couch", "tags": ["speed"], "effects": [{"key": "stat_speed", "value": -20}]},
        {"id": "item_plain", "tags": ["armor"], "effects": [{"key": "stat_armor", "value": 2}]},
    ],
    "characters": [
        _char(
            "character_old",
            flat=[("stat_speed", -10), ("stat_harvesting", 10)],
            pool=["Rock", "Revolver", "Wrench"],
        ),
        _char("character_plain", pool=["Revolver"]),
        _char("character_rounded", flat=[("stat_speed", 5)], pool=["Revolver"]),
        _char("character_chunky", gain=[("stat_speed", -100)], banned=["speed", "lifesteal"]),
        _char("character_locked", flat=[("stat_speed", -15)]),
        _char("character_norow", pool=["Revolver"]),
    ],
    "weapons": [
        {
            "id": "weapon_rock",
            "display_name": "Rock",
            "weapon_type": "melee",
            "sets": ["Primitive", "Blunt"],
            "scaling_stats": [["stat_melee_damage", 1.0]],
        },
        {
            "id": "weapon_rock",
            "display_name": "Rock",
            "weapon_type": "melee",
            "sets": ["Primitive", "Blunt"],
            "scaling_stats": [["stat_melee_damage", 1.0]],
        },
        {
            "id": "weapon_revolver",
            "display_name": "Revolver",
            "weapon_type": "ranged",
            "sets": ["Gun"],
            "scaling_stats": [["stat_ranged_damage", 1.0], ["stat_harvesting", 0.5]],
        },
        {
            "id": "weapon_wrench",
            "display_name": "Wrench",
            "weapon_type": "melee",
            "sets": ["Tool"],
            "scaling_stats": [],
        },
    ],
    "sets": [
        {
            "id": "set_blunt",
            "name": "Blunt",
            "bonuses": [
                {"count": 2, "effects": [{"key": "stat_speed", "value": -2}]},
                {"count": 6, "effects": [{"key": "stat_speed", "value": -10}]},
                {"count": 8, "effects": [{"key": "stat_speed", "value": -99}]},
            ],
        },
        {
            "id": "set_gun",
            "name": "Gun",
            "bonuses": [
                {"count": 2, "effects": [{"key": "stat_armor", "value": 1}]},
            ],
        },
    ],
}


def _state(target="chal_slow", required=None, lists=True, **progress):
    info = {"requires_character": required, "stat": "stat_speed", "number": 0, "value": -20}
    info.update(progress)
    state = {
        "profile": 1,
        "characters": {
            c["id"]: {"unlocked": c["id"] != "character_locked", "unlocked_by": None}
            for c in DATASET["characters"]
        },
        "progress": {target: info},
    }
    if lists:
        state["weapons_unlocked"] = ["weapon_rock", "weapon_revolver", "weapon_wrench"]
    return state


def _ranked(state=None, required=None):
    goal = shape.goal_for("chal_slow", state or _state())
    return fit.rank_characters(goal, DATASET, state or _state(), BUILD_PLANS, required)


def test_character_fit_handles_the_sign_of_a_negative_goal():
    goal = shape.goal_for("chal_slow", _state())
    old = shape.character_goal_fit(DATASET["characters"][0], goal)
    assert (old["base"], old["need"]) == (10, 10)  # -10 speed start is +10 toward -20
    rounded = shape.character_goal_fit(DATASET["characters"][2], goal)
    assert (rounded["base"], rounded["need"]) == (-5, 25)  # +5 start works against it
    assert shape.character_goal_fit(None, goal)["need"] == 20


def test_ranking_orders_by_need_then_row_and_puts_vetoes_last():
    rows = _ranked()
    ids = [r["id"] for r in rows]
    assert ids == [
        "character_old",  # need 10
        "character_plain",  # need 20 with a row
        "character_norow",  # need 20 without
        "character_rounded",  # need 25
        "character_chunky",  # veto sorts last although its need is 20
    ]
    assert "character_locked" not in ids
    chunky = rows[-1]
    assert chunky["veto"] and chunky["banned"] == []  # the speed group holds +speed items
    assert rows[0]["row"] and not rows[2]["row"]
    assert rows[0]["economy"] == 10


def test_banned_groups_list_goal_item_ids_instead_of_tags():
    dataset = {
        **DATASET,
        "items": [
            {
                "id": "item_beanie",
                "tags": ["stat_speed"],
                "effects": [{"key": "stat_speed", "value": 4}],
            },
            {
                "id": "item_other",
                "tags": ["stat_speed"],
                "effects": [{"key": "stat_speed", "value": 2}],
            },
        ],
    }
    goal = shape.Goal("chal_fast", "stat_speed", 50)
    rows = fit.rank_characters(goal, dataset, _state(), BUILD_PLANS, None)
    chunky = next(r for r in rows if r["id"] == "character_chunky")
    assert chunky["banned"] == ["item_beanie"]
    assert "banned item_beanie" in fit._character_line(chunky)


def test_gain_modifier_reports_raw_base_and_need_without_a_veto():
    char = _char("character_x", flat=[("stat_speed", -10)], gain=[("stat_speed", 50)])
    fitted = shape.character_goal_fit(char, shape.goal_for("chal_slow", _state()))
    assert not fitted["veto"]
    assert fitted["start"] == -10 and fitted["base"] == 10
    assert fitted["need"] == pytest.approx(10 / 3)


@pytest.mark.parametrize(
    ("cid", "pct", "need"),
    [("character_entrepreneur", 50, 200 / 1.5), ("character_knight", -80, 1000)],
)
def test_agriculture_gain_modifiers_need_raw_harvesting(cid, pct, need):
    character = _char(cid, gain=[("stat_harvesting", pct)])
    fitted = shape.character_goal_fit(
        character, shape.Goal("chal_agriculture", "stat_harvesting", 200)
    )
    assert not fitted["veto"]
    assert fitted["base"] == 0
    assert fitted["need"] == pytest.approx(need)


@pytest.mark.parametrize("pct", [-100, -150])
def test_nonpositive_gain_multiplier_is_a_veto(pct):
    character = _char("character_x", gain=[("stat_speed", pct)])
    assert shape.character_goal_fit(character, shape.Goal("chal_slow", "stat_speed", -20))["veto"]


def test_requires_character_is_the_only_unlocked_candidate():
    rows = _ranked(_state(required="character_rounded"), required="character_rounded")
    assert [r["id"] for r in rows] == ["character_rounded"]
    lines = fit.fit_lines("chal_slow", DATASET, _state(required="character_plain"), BUILD_PLANS)
    assert "chal_slow requires character_plain: the only candidate" in lines
    assert "Top character: character_plain" in lines


@pytest.mark.parametrize("listed", [True, False])
def test_locked_required_character_stops_fit_without_top_choices(listed):
    state = _state(required="character_locked")
    if not listed:
        state["characters"].pop("character_locked")
    assert _ranked(state, required="character_locked") == []
    lines = fit.fit_lines("chal_slow", DATASET, state, BUILD_PLANS)
    assert "chal_slow requires character_locked: locked" in lines
    assert lines[-1] == "no candidate character"
    assert not any(line.startswith(("Top ", "Starting weapons")) for line in lines)


def test_a_target_without_a_stat_prints_no_stat_goal():
    state = _state(target="chal_gatherer_1", stat="", value=5)
    assert fit.fit_lines("chal_gatherer_1", DATASET, state, BUILD_PLANS) == [
        "no stat goal for chal_gatherer_1"
    ]


def test_weapons_rank_by_set_bonus_then_type_then_scaling():
    old = DATASET["characters"][0]
    goal = shape.goal_for("chal_slow", _state())
    ranked, known = fit.rank_weapons(
        goal, DATASET, _state(), old, fit.plan_row(BUILD_PLANS, old["id"])
    )
    assert known
    assert [w["id"] for w in ranked] == ["weapon_rock", "weapon_revolver", "weapon_wrench"]
    rock = ranked[0]
    assert rock["goal_bonus"] == 10 and rock["sets"] == {"Primitive": 0, "Blunt": 10}
    assert not rock["type_match"]  # melee against the row's ranged
    assert (
        ranked[1]["type_match"] and ranked[1]["scaling"] == 15
    )  # row weights 8 + 7, coefficients unused
    assert not ranked[2]["type_match"]


def test_locked_weapons_are_skipped_and_missing_lists_are_said_so():
    old = DATASET["characters"][0]
    goal = shape.goal_for("chal_slow", _state())
    state = _state()
    state["weapons_unlocked"] = ["weapon_revolver"]
    ranked, _ = fit.rank_weapons(goal, DATASET, state, old, None)
    assert [w["id"] for w in ranked] == ["weapon_revolver"]
    lines = fit.fit_lines("chal_slow", DATASET, _state(lists=False), BUILD_PLANS)
    assert any("lacks weapons_unlocked, treating all as unlocked" in ln for ln in lines)


def test_weapon_type_header_explains_the_unshaped_row_once():
    lines = fit.fit_lines("chal_slow", DATASET, _state(), BUILD_PLANS)
    note = (
        "type match is against the unshaped row; "
        "shaping sets weapon_type to any when it adds prefer_sets"
    )
    assert lines.count(note) == 1
    rock = next(line for line in lines if line.startswith("  weapon_rock:"))
    assert lines.index(note) < lines.index(rock)
    assert "type melee (match no)" in rock


def test_plan_row_parses_type_and_stats():
    assert fit.plan_row(BUILD_PLANS, "character_old") == {
        "weapon_type": "ranged",
        "stats": {"stat_ranged_damage": 8.0, "stat_harvesting": 7.0},
    }
    assert fit.plan_row(BUILD_PLANS, "character_missing") is None


def test_cli_prints_the_top_choices_last(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "unlock_state.json").write_text(json.dumps(_state()), encoding="utf-8")
    (data / "brotato.json").write_text(json.dumps(DATASET), encoding="utf-8")
    root = tmp_path / "root"
    plans = root / fit.BUILD_PLANS
    plans.parent.mkdir(parents=True)
    plans.write_text(BUILD_PLANS, encoding="utf-8")
    real = paths.load()
    monkeypatch.setattr(
        paths,
        "load",
        lambda: real.__class__(**{**real.__dict__, "data_dir": data, "project_root": root}),
    )
    assert cli.main(["proposal", "fit", "--target", "chal_slow"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "Top weapon: weapon_rock"
    assert "Top character: character_old" in lines
    assert (
        cli.main(["proposal", "fit", "--target", "chal_slow", "--character", "character_plain"])
        == 0
    )
    assert capsys.readouterr().out.splitlines()[-1] == "Top weapon: weapon_revolver"
