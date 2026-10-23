import json
import os
from pathlib import Path

from brotato_bot import cli

FIXTURE = Path(__file__).parent / "fixtures" / "state_shop.json"
CHARACTER = "character_well_rounded"


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


def _advise_state(tmp_path, levelup=True):
    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state["kind"] = "advise"
    if levelup:
        state["levelup_options"] = [
            {"id": "stat_armor", "stat": "stat_armor", "value": 1, "advisor_score": 3.0},
        ]
    path = tmp_path / "advise_state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def test_advise_context_prints_both_offer_kinds_and_no_answer_format(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    path = _advise_state(tmp_path)
    assert cli.main(["advise-context", str(path)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == f"# State file: {path}"
    assert CHARACTER in out
    assert "option_index 0: weapon_smg_1" in out  # a shop offer
    assert "option_index 2: stat_armor" in out  # the level-up offer, after the two shop slots
    assert "Response schema" not in out


def test_advise_context_without_argument_and_no_advise_state_exits_1(monkeypatch, capsys, tmp_path):
    state_dir = _env(monkeypatch, tmp_path)
    assert cli.main(["advise-context"]) == 1
    assert "no advise state file" in capsys.readouterr().out
    assert list(state_dir.iterdir()) == []


def test_advise_context_picks_the_newest_advise_file(monkeypatch, capsys, tmp_path):
    state_dir = _env(monkeypatch, tmp_path)
    shop = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert shop["kind"] == "shop"
    (state_dir / "shop.json").write_text(json.dumps(shop), encoding="utf-8")
    advise = _advise_state(state_dir, levelup=False)
    advise.rename(state_dir / "advise.json")
    newer = state_dir / "advise.json"
    later = newer.stat().st_mtime + 10
    os.utime(state_dir / "shop.json", (later, later))  # shop is newer, but not advise
    assert cli.main(["advise-context"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first == f"# State file: {newer}"
