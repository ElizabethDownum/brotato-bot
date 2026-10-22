from pathlib import Path

from brotato_bot import paths


def test_default_paths_match_spec():
    p = paths.load({"APPDATA": r"C:\Users\x\AppData\Roaming"})
    app = Path(r"C:\Users\x\AppData\Roaming")
    assert p.game_dir == Path(r"D:\SteamLibrary\steamapps\common\Brotato")
    assert p.pck == p.game_dir / "Brotato.pck"
    assert p.save_dir == app / "Brotato" / "<steam64 id>"
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
