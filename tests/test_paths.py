from pathlib import Path

import pytest

from brotato_bot import paths

FAKE_ID = "76561190000000000"


def _appdata(tmp_path, *names):
    for n in names:
        (tmp_path / "Brotato" / n).mkdir(parents=True)
    return tmp_path


def test_default_paths_match_spec(tmp_path):
    app = _appdata(tmp_path, FAKE_ID, "brotato-bot")
    p = paths.load({"APPDATA": str(app)})
    assert p.game_dir == Path(r"D:\SteamLibrary\steamapps\common\Brotato")
    assert p.pck == p.game_dir / "Brotato.pck"
    assert p.dlc_pck == p.game_dir / "BrotatoAbyssalTerrors.pck"
    assert p.save_dir == app / "Brotato" / FAKE_ID
    assert p.settings_json == p.save_dir / "settings.json"
    assert p.mod_user_dir == app / "Brotato" / "brotato-bot"
    assert p.plan_json == p.mod_user_dir / "plan.json"
    assert p.config_json == p.mod_user_dir / "config.json"
    assert p.runs_in == p.mod_user_dir / "runs"
    assert p.state_dir == p.mod_user_dir / "state"
    assert p.requests_dir == p.mod_user_dir / "requests"
    assert p.responses_dir == p.mod_user_dir / "responses"
    root = Path(paths.__file__).resolve().parent.parent
    assert p.project_root == root
    assert p.data_dir == root / "data"
    assert p.knowledge_dir == root / "knowledge"
    assert p.knowledge_cache == root / "knowledge" / "cache"
    assert p.runs_out == root / "runs"
    assert p.decisions_dir == root / "decisions"
    assert p.proposals_dir == root / "proposals"
    assert p.advice_dir == root / "advice"


def test_env_override():
    p = paths.load({"APPDATA": "C:/a", "BROTATO_BOT_MOD_USER_DIR": "/tmp/x"})
    assert p.plan_json == Path("/tmp/x") / "plan.json"
    assert p.runs_in == Path("/tmp/x") / "runs"


def test_child_override_wins_and_project_root_moves_children():
    p = paths.load(
        {
            "APPDATA": "C:/a",
            "BROTATO_BOT_PROJECT_ROOT": "/p",
            "BROTATO_BOT_ADVICE_DIR": "/elsewhere",
        }
    )
    assert p.data_dir == Path("/p") / "data"
    assert p.advice_dir == Path("/elsewhere")


def test_missing_appdata_raises(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    with pytest.raises(RuntimeError, match="APPDATA"):
        paths.load({})


def test_paths_dlc_pck_override():
    p = paths.load({"APPDATA": "C:/a", "BROTATO_BOT_DLC_PCK": "/x/dlc.pck"})
    assert p.dlc_pck == Path("/x/dlc.pck")
    moved = paths.load({"APPDATA": "C:/a", "BROTATO_BOT_GAME_DIR": "/g"})
    assert moved.dlc_pck == Path("/g") / "BrotatoAbyssalTerrors.pck"


def test_knowledge_dir_override_moves_cache():
    p = paths.load({"APPDATA": "C:/a", "BROTATO_BOT_KNOWLEDGE_DIR": "/k"})
    assert p.knowledge_dir == Path("/k")
    assert p.knowledge_cache == Path("/k") / "cache"


def test_save_dir_needs_exactly_one_steam64_folder(tmp_path):
    app = _appdata(tmp_path, "brotato-bot", "1234", "7656119000000000x")
    p = paths.load({"APPDATA": str(app)})  # loading never scans
    assert p.plan_json == app / "Brotato" / "brotato-bot" / "plan.json"
    with pytest.raises(RuntimeError, match="no Steam64 save folder.*BROTATO_BOT_SAVE_DIR"):
        _ = p.save_dir

    (app / "Brotato" / FAKE_ID).mkdir()
    assert paths.load({"APPDATA": str(app)}).save_dir == app / "Brotato" / FAKE_ID

    (app / "Brotato" / "76561190000000001").mkdir()
    two = paths.load({"APPDATA": str(app)})
    with pytest.raises(RuntimeError, match="2 Steam64 save folders"):
        _ = two.settings_json


def test_save_dir_without_brotato_folder_raises_on_access(tmp_path):
    p = paths.load({"APPDATA": str(tmp_path)})
    with pytest.raises(RuntimeError, match="BROTATO_BOT_STEAM_ID"):
        _ = p.save_dir


def test_save_dir_env_overrides_skip_the_scan(tmp_path):
    app = _appdata(tmp_path, FAKE_ID, "76561190000000001")
    by_id = paths.load({"APPDATA": str(app), "BROTATO_BOT_STEAM_ID": "76561190000000001"})
    assert by_id.save_dir == app / "Brotato" / "76561190000000001"
    by_dir = paths.load({"APPDATA": str(app), "BROTATO_BOT_SAVE_DIR": "/saves"})
    assert by_dir.save_dir == Path("/saves")
    assert by_dir.settings_json == Path("/saves") / "settings.json"
    own = paths.load({"APPDATA": str(app), "BROTATO_BOT_SETTINGS_JSON": "/s.json"})
    assert own.settings_json == Path("/s.json")  # no save dir needed
