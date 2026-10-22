"""Single source of truth for filesystem locations; every path is env-overridable."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_PREFIX = "BROTATO_BOT_"
DEFAULT_GAME_DIR = r"D:\SteamLibrary\steamapps\common\Brotato"
DLC_PCK_NAME = "BrotatoAbyssalTerrors.pck"
STEAM_ID = "<steam64 id>"


@dataclass(frozen=True)
class Paths:
    game_dir: Path
    pck: Path
    dlc_pck: Path
    save_dir: Path
    settings_json: Path
    mod_user_dir: Path
    plan_json: Path
    config_json: Path
    runs_in: Path
    state_dir: Path
    requests_dir: Path
    responses_dir: Path
    project_root: Path
    data_dir: Path
    knowledge_cache: Path
    runs_out: Path
    decisions_dir: Path
    proposals_dir: Path
    advice_dir: Path


def load(env: Mapping[str, str] | None = None) -> Paths:
    e: Mapping[str, str] = os.environ if env is None else env

    def ov(name: str, default: Path) -> Path:
        v = e.get(ENV_PREFIX + name.upper())
        return Path(v) if v else default

    appdata = e.get("APPDATA") or os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set (in the passed mapping or os.environ)")
    brotato_appdata = Path(appdata) / "Brotato"

    game_dir = ov("game_dir", Path(DEFAULT_GAME_DIR))
    pck = ov("pck", game_dir / "Brotato.pck")
    dlc_pck = ov("dlc_pck", game_dir / DLC_PCK_NAME)
    save_dir = ov("save_dir", brotato_appdata / STEAM_ID)
    settings_json = ov("settings_json", save_dir / "settings.json")
    mod_user_dir = ov("mod_user_dir", brotato_appdata / "brotato-bot")
    project_root = ov("project_root", Path(__file__).resolve().parent.parent)

    return Paths(
        game_dir=game_dir,
        pck=pck,
        dlc_pck=dlc_pck,
        save_dir=save_dir,
        settings_json=settings_json,
        mod_user_dir=mod_user_dir,
        plan_json=ov("plan_json", mod_user_dir / "plan.json"),
        config_json=ov("config_json", mod_user_dir / "config.json"),
        runs_in=ov("runs_in", mod_user_dir / "runs"),
        state_dir=ov("state_dir", mod_user_dir / "state"),
        requests_dir=ov("requests_dir", mod_user_dir / "requests"),
        responses_dir=ov("responses_dir", mod_user_dir / "responses"),
        project_root=project_root,
        data_dir=ov("data_dir", project_root / "data"),
        knowledge_cache=ov("knowledge_cache", project_root / "knowledge" / "cache"),
        runs_out=ov("runs_out", project_root / "runs"),
        decisions_dir=ov("decisions_dir", project_root / "decisions"),
        proposals_dir=ov("proposals_dir", project_root / "proposals"),
        advice_dir=ov("advice_dir", project_root / "advice"),
    )
