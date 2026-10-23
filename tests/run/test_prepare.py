import json

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
    state = {"characters": {"character_well_rounded": {"unlocked": unlocked, "unlocked_by": None}}}
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
