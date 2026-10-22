import json
from pathlib import Path

from brotato_bot import cli
from brotato_bot.dataset import unlocks
from brotato_bot.dataset.keys import generate_hash

FIXTURES = Path(__file__).parent / "fixtures"
CHALLENGES = FIXTURES  # build_graph takes the extracted root holding challenges/


def _graph():
    return unlocks.build_graph(CHALLENGES, FIXTURES / "translations.csv")


def _save(completed=(), characters=()):
    save = json.loads((FIXTURES / "save_min.json").read_text(encoding="utf-8"))
    save["challenges_completed"] = [
        generate_hash(c) if isinstance(c, str) else c for c in completed
    ]
    save["characters_unlocked"] = save["characters_unlocked"] + [
        generate_hash(c) for c in characters
    ]
    return save


def _by_id(graph):
    return {c.id: c for c in graph}


def test_build_graph_reads_reward_kind():
    g = _by_id(_graph())
    arms = g["chal_arms_dealer"]
    assert arms.reward_kind == "item"
    assert arms.reward_id == "anvil"
    assert arms.hash == generate_hash("chal_arms_dealer")
    assert arms.requires_character == "character_arms_dealer"
    assert arms.name_key == "CHARACTER_ARMS_DEALER"
    assert arms.name_en == "Arms Dealer"
    assert arms.unlocked_by_default is False
    assert g["chal_mage"].reward_kind == "weapon"
    assert g["chal_mage"].reward_id == "test_wand_2"
    robust = g["chal_robust"]
    assert robust.reward_kind == "character"
    assert robust.reward_id == "lich"
    assert robust.requires_character is None
    assert robust.stat == "stat_max_hp"


def test_build_graph_falls_back_to_keys_without_translations(tmp_path):
    g = _by_id(unlocks.build_graph(CHALLENGES, tmp_path / "missing.csv"))
    assert g["chal_robust"].name_en == "CHAL_ROBUST"


def test_unlock_state_splits_done_open():
    save = _save(completed=["chal_robust"], characters=["character_arms_dealer", "character_mage"])
    state = unlocks.unlock_state(_graph(), save, 0)
    assert state["done"] == ["chal_robust"]
    assert state["open"] == ["chal_arms_dealer", "chal_mage"]
    assert state["blocked"] == []
    assert state["unknown"] == []
    assert state["characters"]["character_lich"] == {
        "unlocked": False,
        "unlocked_by": "chal_robust",
    }
    # well_rounded is unlocked in the save but no fixture challenge names it.
    assert "character_well_rounded" not in state["characters"]
    assert state["unknown_characters"] == [generate_hash("character_well_rounded")]
    assert "chal_robust" not in state["progress"]
    assert state["progress"]["chal_arms_dealer"] == {
        "requires_character": "character_arms_dealer",
        "stat": "",
        "number": 0,
    }


def test_unknown_hashes_are_reported():
    save = _save(completed=["chal_robust", 12345])
    state = unlocks.unlock_state(_graph(), save, 0)
    assert state["unknown"] == [12345]
    assert state["done"] == ["chal_robust"]


def test_blocked_when_required_character_locked():
    save = _save(characters=["character_arms_dealer"])  # mage stays locked
    state = unlocks.unlock_state(_graph(), save, 0)
    assert "chal_mage" in state["blocked"]
    assert "chal_mage" not in state["open"]
    assert state["characters"]["character_mage"]["unlocked"] is False
    assert state["progress"]["chal_mage"]["requires_character"] == "character_mage"


def test_unlock_state_command_writes_json(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    (data_dir / "extracted").mkdir(parents=True)
    import shutil

    shutil.copytree(FIXTURES / "challenges", data_dir / "extracted" / "challenges")
    shutil.copy(FIXTURES / "translations.csv", data_dir / "translations.csv")
    save_dir = tmp_path / "save"
    save_dir.mkdir()
    (save_dir / "save_v3_2.json").write_text(
        json.dumps(_save(completed=["chal_robust"])), encoding="utf-8"
    )
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BROTATO_BOT_SAVE_DIR", str(save_dir))

    assert cli.main(["unlock-state", "--profile", "2"]) == 0
    out = json.loads((data_dir / "unlock_state.json").read_text(encoding="utf-8"))
    assert out["profile"] == 2
    assert out["done"] == ["chal_robust"]
    assert out["blocked"] == ["chal_arms_dealer", "chal_mage"]


def test_unlock_state_command_missing_save(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BROTATO_BOT_SAVE_DIR", str(tmp_path / "nosave"))
    assert cli.main(["unlock-state"]) == 1
    assert "save" in capsys.readouterr().err
