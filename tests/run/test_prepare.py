import json
import re

import pytest

from brotato_bot import cli
from brotato_bot.run import prepare

PLAN = {
    "plan_id": "well-rounded-v1",
    "character_id": "character_well_rounded",
    "plan": {"weapon_type": "ranged"},
}


def _settings(p, profile_id, pause):
    p.settings_json.parent.mkdir(parents=True, exist_ok=True)
    p.settings_json.write_text(
        json.dumps({"current_profile_id": profile_id, "settings": {"pause_on_focus_lost": pause}}),
        encoding="utf-8",
    )


def test_prepare_writes_plan_and_target_and_warns(tmp_paths):
    p = tmp_paths
    _settings(p, 0, True)
    p.config_json.parent.mkdir(parents=True, exist_ok=True)
    p.config_json.write_text(json.dumps({"bot_profile_id": 1, "ask_floor": 5.0}), encoding="utf-8")

    warnings = prepare.prepare(PLAN, "chal_gatherer_1", p)

    assert json.loads(p.plan_json.read_text(encoding="utf-8")) == PLAN
    config = json.loads(p.config_json.read_text(encoding="utf-8"))
    assert config == {"bot_profile_id": 1, "ask_floor": 5.0, "target_challenge": "chal_gatherer_1"}
    assert "pause_on_focus_lost is true" in warnings
    assert "current_profile_id is 0" in warnings


def test_prepare_creates_config_with_only_target_and_no_warnings(tmp_paths):
    p = tmp_paths
    _settings(p, 1, False)
    warnings = prepare.prepare(PLAN, "chal_x", p)
    assert json.loads(p.config_json.read_text(encoding="utf-8")) == {"target_challenge": "chal_x"}
    assert not any("pause_on_focus_lost" in w or "current_profile_id" in w for w in warnings)


def test_prepare_without_target_clears_it(tmp_paths):
    p = tmp_paths
    _settings(p, 1, False)
    p.config_json.parent.mkdir(parents=True, exist_ok=True)
    p.config_json.write_text(json.dumps({"target_challenge": "old"}), encoding="utf-8")
    prepare.prepare(PLAN, None, p)
    assert json.loads(p.config_json.read_text(encoding="utf-8")) == {"target_challenge": ""}


def test_prepare_bot_profile_id_from_config(tmp_paths):
    p = tmp_paths
    _settings(p, 2, False)
    p.config_json.parent.mkdir(parents=True, exist_ok=True)
    p.config_json.write_text(json.dumps({"bot_profile_id": 2}), encoding="utf-8")
    warnings = prepare.prepare(PLAN, None, p)
    assert not any("current_profile_id" in w for w in warnings)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2, 2),
        (2.0, 2),
        (2.7, 2),
        (0, 1),
        (0.0, 1),
        (-3, 1),
        (True, 1),
        ("2", 1),
        (None, 1),
        (float("nan"), 1),
        (float("inf"), 1),
        (10**400, 10**400),
    ],
)
def test_bot_profile_id_normalizes_like_the_mod(value, expected):
    assert prepare.bot_profile_id({"bot_profile_id": value}) == expected


def test_prepare_warns_when_settings_missing(tmp_paths):
    warnings = prepare.prepare(PLAN, None, tmp_paths)
    assert any("settings.json" in w for w in warnings)
    assert tmp_paths.plan_json.is_file()


@pytest.mark.parametrize(
    "bad",
    [
        {"character_id": "c", "plan": {}},
        {"plan_id": "x", "plan": {}},
        {"plan_id": "x", "character_id": "c"},
        {"plan_id": "x", "character_id": "c", "plan": []},
        {"plan_id": "", "character_id": "c", "plan": {}},
        ["not", "an", "object"],
    ],
)
def test_prepare_refuses_bad_plan(tmp_paths, bad):
    with pytest.raises(ValueError):
        prepare.prepare(bad, None, tmp_paths)
    assert not tmp_paths.plan_json.exists()
    assert not tmp_paths.config_json.exists()


def test_prepare_cli(tmp_paths, tmp_path, capsys):
    _settings(tmp_paths, 1, False)
    plan_file = tmp_path / "plan_in.json"
    plan_file.write_text(json.dumps(PLAN), encoding="utf-8")
    assert cli.main(["prepare", "--plan", str(plan_file), "--target", "chal_y"]) == 0
    assert json.loads(tmp_paths.plan_json.read_text(encoding="utf-8")) == PLAN
    config = json.loads(tmp_paths.config_json.read_text(encoding="utf-8"))
    assert config["target_challenge"] == "chal_y"


def test_prepare_cli_bad_plan_returns_1(tmp_paths, tmp_path, capsys):
    plan_file = tmp_path / "plan_in.json"
    plan_file.write_text(json.dumps({"plan_id": "x"}), encoding="utf-8")
    assert cli.main(["prepare", "--plan", str(plan_file)]) == 1
    assert not tmp_paths.plan_json.exists()


def _proposal_file(tmp_path, text):
    path = tmp_path / "2026-10-22-001.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _unlock_state(p, unlocked):
    p.data_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "characters": {"character_well_rounded": {"unlocked": unlocked, "unlocked_by": None}},
        "done": [],
        "open": ["chal_gatherer_1"],
        "blocked": [],
        "progress": {"chal_gatherer_1": {"requires_character": None, "value": 5}},
        "profile": 1,
    }
    p.data_dir.joinpath("unlock_state.json").write_text(json.dumps(state), encoding="utf-8")


def test_prepare_from_proposal_installs_plan_and_target(tmp_paths, tmp_path, proposal_md, capsys):
    _settings(tmp_paths, 1, False)
    _unlock_state(tmp_paths, True)
    path = _proposal_file(tmp_path, proposal_md())
    assert cli.main(["prepare", "--from-proposal", path]) == 0
    assert (
        json.loads(tmp_paths.plan_json.read_text(encoding="utf-8"))["plan_id"] == "well-rounded-v1"
    )
    config = json.loads(tmp_paths.config_json.read_text(encoding="utf-8"))
    assert config["target_challenge"] == "chal_gatherer_1"


def test_prepare_from_proposal_writes_the_target_into_the_plan(tmp_paths, tmp_path, proposal_md):
    # O8/S2: the installed plan.json carries the validated target ("" for none).
    _settings(tmp_paths, 1, False)
    _unlock_state(tmp_paths, True)
    assert cli.main(["prepare", "--from-proposal", _proposal_file(tmp_path, proposal_md())]) == 0
    plan = json.loads(tmp_paths.plan_json.read_text(encoding="utf-8"))
    assert plan["target_challenge"] == "chal_gatherer_1"
    none = proposal_md().replace("- target: chal_gatherer_1", "- target: none")
    assert cli.main(["prepare", "--from-proposal", _proposal_file(tmp_path, none)]) == 0
    assert json.loads(tmp_paths.plan_json.read_text(encoding="utf-8"))["target_challenge"] == ""


def test_prepare_from_proposal_refuses_an_unchanged_plan_after_stagnation(
    tmp_paths, tmp_path, proposal_md, capsys
):
    # O1: prepare loads runs/index.json and applies the material-change check.
    _unlock_state(tmp_paths, True)
    rows = [
        {
            "run_id": f"r{i}",
            "character_id": "character_well_rounded",
            "plan_id": f"a-v{i}",
            "target_challenge": "chal_gatherer_1",
            "outcome": "death",
            "death_wave": 10,
            "hp_end_last_wave": 5,
            "profile_id": 1,
        }
        for i in (1, 2, 3)
    ]
    tmp_paths.runs_out.mkdir(parents=True, exist_ok=True)
    (tmp_paths.runs_out / "index.json").write_text(json.dumps(rows), encoding="utf-8")
    path = _proposal_file(tmp_path, proposal_md(plan_id="a-v4"))
    assert cli.main(["prepare", "--from-proposal", path]) == 1
    assert "prepare: stagnation is stagnant on chal_gatherer_1" in capsys.readouterr().out
    assert not tmp_paths.plan_json.exists()


def test_prepare_rejects_locked_character(tmp_paths, tmp_path, proposal_md, capsys):
    _unlock_state(tmp_paths, False)
    path = _proposal_file(tmp_path, proposal_md())
    assert cli.main(["prepare", "--from-proposal", path]) == 1
    assert "character_well_rounded is locked" in capsys.readouterr().out
    assert not tmp_paths.plan_json.exists()


def test_prepare_from_proposal_needs_unlock_state(tmp_paths, tmp_path, proposal_md, capsys):
    path = _proposal_file(tmp_path, proposal_md())
    assert cli.main(["prepare", "--from-proposal", path]) == 1
    assert "unlock-state --profile 1" in capsys.readouterr().out
    assert not tmp_paths.plan_json.exists()


def test_prepare_plan_and_from_proposal_are_exclusive(tmp_paths, tmp_path, proposal_md):
    path = _proposal_file(tmp_path, proposal_md())
    with pytest.raises(SystemExit):
        cli.main(["prepare", "--plan", path, "--from-proposal", path])
    with pytest.raises(SystemExit):
        cli.main(["prepare"])


def _launch(p):
    return json.loads(p.plan_json.with_name("launch.json").read_text(encoding="utf-8"))


def test_prepare_from_proposal_writes_the_launch_contract(tmp_paths, tmp_path, proposal_md, capsys):
    _settings(tmp_paths, 1, False)
    _unlock_state(tmp_paths, True)
    text = proposal_md(starting_weapon="weapon_rock").replace("- danger: 0", "- danger: 2")
    assert cli.main(["prepare", "--from-proposal", _proposal_file(tmp_path, text)]) == 0
    out = capsys.readouterr().out
    assert "launch token written" in out
    assert "load the bot profile by hand" in out
    plan = json.loads(tmp_paths.plan_json.read_text(encoding="utf-8"))
    assert (plan["danger"], plan["starting_weapon"]) == (2, "weapon_rock")
    assert plan["target_challenge"] == "chal_gatherer_1"
    launch = _launch(tmp_paths)
    assert launch["token"].startswith("2026-10-22-001-")
    assert re.fullmatch(r"2026-10-22-001-\d{8}T\d{6}Z", launch["token"])
    assert {k: v for k, v in launch.items() if k not in ("token", "created_at")} == {
        "character_id": "character_well_rounded",
        "starting_weapon": "weapon_rock",
        "danger": 2,
        "target_challenge": "chal_gatherer_1",
    }
    assert launch["created_at"].endswith("+00:00")


def test_prepare_overwrites_a_stale_launch_token(tmp_paths, tmp_path, proposal_md):
    _settings(tmp_paths, 1, False)
    _unlock_state(tmp_paths, True)
    stale = tmp_paths.plan_json.with_name("launch.json")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(json.dumps({"token": "stale"}), encoding="utf-8")
    assert cli.main(["prepare", "--from-proposal", _proposal_file(tmp_path, proposal_md())]) == 0
    assert _launch(tmp_paths)["token"] != "stale"
    assert _launch(tmp_paths)["starting_weapon"] == "any"


def test_prepare_plan_with_flags_writes_the_contract_and_without_removes_a_stale_one(
    tmp_paths, tmp_path, capsys
):
    plan_file = tmp_path / "plan_in.json"
    plan_file.write_text(
        json.dumps({"plan_id": "old-v1", "character_id": "character_old", "plan": {}}),
        encoding="utf-8",
    )
    args = ["prepare", "--plan", str(plan_file), "--target", "chal_slow"]
    assert cli.main([*args, "--danger", "1", "--starting-weapon", "weapon_rock"]) == 0
    launch = _launch(tmp_paths)
    assert launch["token"].startswith("old-v1-")
    assert (launch["danger"], launch["starting_weapon"]) == (1, "weapon_rock")
    assert launch["target_challenge"] == ""  # the plan file's own key, which is unset here
    assert cli.main(args) == 0
    assert not tmp_paths.plan_json.with_name("launch.json").exists()
    assert "launch token written" not in capsys.readouterr().out.split("Wrote", 2)[-1]


def test_prepare_from_proposal_refuses_the_plan_only_flags(tmp_paths, tmp_path, proposal_md):
    path = _proposal_file(tmp_path, proposal_md())
    assert cli.main(["prepare", "--from-proposal", path, "--danger", "1"]) == 1


def test_prepare_plan_rejects_out_of_range_danger_before_writing(tmp_paths, tmp_path, capsys):
    plan_file = tmp_path / "plan_in.json"
    plan_file.write_text(json.dumps(PLAN), encoding="utf-8")
    assert cli.main(["prepare", "--plan", str(plan_file), "--danger", "9"]) == 1
    assert "danger must be between 0 and 5" in capsys.readouterr().out
    assert not tmp_paths.plan_json.exists()
    assert not tmp_paths.config_json.exists()
    assert not tmp_paths.plan_json.with_name("launch.json").exists()


@pytest.mark.parametrize("danger", [0, prepare.MAX_DANGER])
def test_validate_plan_accepts_danger_boundaries(danger):
    prepare.validate_plan({**PLAN, "danger": danger})


@pytest.mark.parametrize(
    "extra",
    [
        {"danger": "2"},
        {"danger": True},
        {"danger": -1},
        {"danger": 6},
        {"danger": 9},
        {"starting_weapon": ""},
        {"plan": {"prefer_sets": {"set_blunt": "x"}}},
        {"plan": {"prefer_sets": []}},
        {"plan": {"prefer_sets": {"set_blunt": True}}},
    ],
)
def test_validate_plan_checks_the_launch_keys(extra):
    base = {"plan_id": "x", "character_id": "c", "plan": {}}
    with pytest.raises(ValueError):
        prepare.validate_plan({**base, **extra})
    prepare.validate_plan(
        {
            **base,
            "danger": 2,
            "starting_weapon": "any",
            "plan": {"prefer_sets": {"set_blunt": 12.5}},
        }
    )
