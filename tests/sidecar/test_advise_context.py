import json
import os
from pathlib import Path

import pytest

from brotato_bot import cli
from brotato_bot.sidecar import prompt

FIXTURE = Path(__file__).parent / "fixtures" / "state_shop.json"
CHARACTER = "character_well_rounded"
# The exporter's shape (state_export.gd): no "id" key.
LEVELUP = [{"index": 0, "stat": "stat_armor", "value": 1, "advisor_score": 3.0}]


def _env(monkeypatch, tmp_path):
    """Point every path the advise command reads at tmp_path; the data dir stays empty."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("BROTATO_BOT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("BROTATO_BOT_ADVICE_DIR", str(tmp_path / "advice"))
    monkeypatch.setenv("BROTATO_BOT_PLAN_JSON", str(tmp_path / "plan.json"))
    monkeypatch.setenv("BROTATO_BOT_CONFIG_JSON", str(tmp_path / "config.json"))
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BROTATO_BOT_KNOWLEDGE_CACHE", str(tmp_path / "cache"))
    (tmp_path / "state").mkdir(exist_ok=True)
    return tmp_path / "state"


def _write_state(path, **edits):
    """An advise state from the shop fixture, with one level-up offer, plus field edits."""
    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state["kind"] = "advise"
    state["levelup_options"] = list(LEVELUP)
    state.update(edits)
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _touch(path, when):
    os.utime(path, (when, when))


def test_advise_context_prints_shop_and_levelup_offers_and_no_answer_format(
    monkeypatch, capsys, tmp_path
):
    _env(monkeypatch, tmp_path)
    path = _write_state(tmp_path / "advise.json")
    assert cli.main(["advise-context", str(path)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == f"# State file: {path}"
    assert lines[1] == f"# Advice dir: {tmp_path / 'advice'}"
    for section in ("## Objective", "## State", "## Options"):
        assert section in out
    assert CHARACTER in out
    assert "option_index 0: weapon_smg_1" in out  # a shop offer
    assert "option_index 2: stat_armor" in out  # the level-up offer, after the two shop slots
    assert "option_index 2: stat_armor: stat_armor +1, advisor score 3" in out
    assert "## Answer format" not in out
    assert "Answer with only one JSON object" not in out


def test_advise_context_without_argument_and_no_advise_state_exits_1(monkeypatch, capsys, tmp_path):
    state_dir = _env(monkeypatch, tmp_path)
    assert cli.main(["advise-context"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"advise-context: no advise state file in {state_dir}"
    assert list(state_dir.iterdir()) == []


def test_newest_of_several_advise_files_wins(monkeypatch, capsys, tmp_path):
    state_dir = _env(monkeypatch, tmp_path)
    oldest = _write_state(state_dir / "a.json")
    middle = _write_state(state_dir / "c.json")
    newest = _write_state(state_dir / "b.json")  # alphabetically first, but newest
    _touch(oldest, 1_000_000_000)
    _touch(middle, 1_000_000_100)
    _touch(newest, 1_000_000_200)
    assert cli.main(["advise-context"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"# State file: {newest}"


def test_newest_advise_pick_skips_unreadable_and_non_advise_files(monkeypatch, capsys, tmp_path):
    state_dir = _env(monkeypatch, tmp_path)
    good = _write_state(state_dir / "good.json")
    _touch(good, 1_000_000_000)  # the oldest of everything below
    junk = {
        "bad_json.json": b"{not json",
        "bad_utf8.json": b"\xff\xfe\x00bad",
        "list.json": b"[1, 2]",
        "shop.json": json.dumps({"kind": "shop", "character_id": CHARACTER}).encode(),
    }
    for name, data in junk.items():
        (state_dir / name).write_bytes(data)
        _touch(state_dir / name, 1_000_000_500)  # newer than the good advise file
    (state_dir / "dir.json").mkdir()
    _touch(state_dir / "dir.json", 1_000_000_500)
    assert cli.main(["advise-context"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"# State file: {good}"


def test_explicit_non_object_state_is_one_error_line(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    path = tmp_path / "list_state.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert cli.main(["advise-context", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"advise-context: {path} is not a JSON object"


@pytest.mark.parametrize(
    "edits, message",
    [
        ({"character_id": None}, "needs a non-empty string character_id"),
        ({"character_id": ""}, "needs a non-empty string character_id"),
        ({"wave": "2"}, "needs an integer wave"),
        ({"wave": None}, "needs an integer wave"),
    ],
)
def test_missing_identity_fields_are_refused(monkeypatch, capsys, tmp_path, edits, message):
    _env(monkeypatch, tmp_path)
    path = _write_state(tmp_path / "advise.json", **edits)
    assert cli.main(["advise-context", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"advise-context: {path} {message}"


@pytest.mark.parametrize("edits", [{"shop": 5}, {"stats": [1, 2]}, {"weapons": 7}])
def test_a_state_that_cannot_build_gives_one_error_line_and_no_output(
    monkeypatch, capsys, tmp_path, edits
):
    _env(monkeypatch, tmp_path)
    path = _write_state(tmp_path / "advise.json", **edits)
    assert cli.main(["advise-context", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"advise-context: cannot build the context from {path}: ")
    assert captured.err.count("\n") == 1


def _write_plan(tmp_path, **edits):
    plan = {
        "plan_id": "well-rounded-v1",
        "character_id": CHARACTER,
        "target_challenge": "chal_bot_target",
        "plan": {"weapon_type": "ranged"},
    }
    plan.update(edits)
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")


def test_advise_context_uses_a_matching_plan_but_no_target(monkeypatch, capsys, tmp_path):
    # O5/S6: the owner's run gets the plan only when it is the run's plan, and no bot target.
    _env(monkeypatch, tmp_path)
    _write_plan(tmp_path)
    path = _write_state(tmp_path / "advise.json")
    assert cli.main(["advise-context", str(path)]) == 0
    out = capsys.readouterr().out
    plan = out[out.find("## Plan") : out.find("## Relevant knowledge")]
    assert '"plan_id":"well-rounded-v1"' in plan
    assert '"weapon_type":"ranged"' in plan
    assert "Target challenge" not in out
    assert "chal_bot_target" not in out
    assert "chal_gatherer_1" not in out.split("## State")[0]
    assert prompt.NO_TARGET in out


@pytest.mark.parametrize("edits", [{"character_id": "character_other"}, {"plan_id": "other-v1"}])
def test_advise_context_drops_a_plan_for_another_run(monkeypatch, capsys, tmp_path, edits):
    _env(monkeypatch, tmp_path)
    _write_plan(tmp_path, **edits)
    path = _write_state(tmp_path / "advise.json")
    assert cli.main(["advise-context", str(path)]) == 0
    out = capsys.readouterr().out
    plan = out[out.find("## Plan") : out.find("## Relevant knowledge")]
    assert "No plan file" in plan
    assert "character_other" not in out
    assert "other-v1" not in out
    assert "chal_bot_target" not in out
    assert prompt.NO_TARGET in out
