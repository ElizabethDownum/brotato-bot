import pytest

from brotato_bot import paths


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Paths with every location the run commands touch redirected into tmp_path."""
    env = {
        "APPDATA": str(tmp_path / "appdata"),
        "BROTATO_BOT_SAVE_DIR": str(tmp_path / "save"),
        "BROTATO_BOT_MOD_USER_DIR": str(tmp_path / "mod"),
        "BROTATO_BOT_PROJECT_ROOT": str(tmp_path / "project"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return paths.load(env)
