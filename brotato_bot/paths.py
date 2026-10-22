"""Single source of truth for filesystem locations; every path is env-overridable."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

ENV_PREFIX = "BROTATO_BOT_"
DEFAULT_GAME_DIR = r"D:\SteamLibrary\steamapps\common\Brotato"
DLC_PCK_NAME = "BrotatoAbyssalTerrors.pck"
# The game keeps saves in %APPDATA%\Brotato\<Steam64 id>; the id is found at runtime
# (never stored here) so the repository does not publish it.
_STEAM64_DIR = re.compile(r"\d{17}")


@dataclass(frozen=True)
class Paths:
    game_dir: Path
    pck: Path
    dlc_pck: Path
    mod_user_dir: Path
    plan_json: Path
    config_json: Path
    runs_in: Path
    state_dir: Path
    requests_dir: Path
    responses_dir: Path
    project_root: Path
    data_dir: Path
    knowledge_dir: Path
    knowledge_cache: Path
    runs_out: Path
    decisions_dir: Path
    proposals_dir: Path
    advice_dir: Path
    brotato_appdata: Path
    save_dir_override: Path | None = None
    steam_id: str | None = None
    settings_json_override: Path | None = None

    @cached_property
    def save_dir(self) -> Path:
        """``BROTATO_BOT_SAVE_DIR``, else ``%APPDATA%/Brotato/<BROTATO_BOT_STEAM_ID>``,
        else the single 17-digit (Steam64) folder under ``%APPDATA%/Brotato``. Resolved
        on first access, so commands that never read a save run without the game."""
        if self.save_dir_override is not None:
            return self.save_dir_override
        if self.steam_id:
            return self.brotato_appdata / self.steam_id
        root = self.brotato_appdata
        found = (
            sorted(d for d in root.iterdir() if d.is_dir() and _STEAM64_DIR.fullmatch(d.name))
            if root.is_dir()
            else []
        )
        if len(found) == 1:
            return found[0]
        what = "no Steam64 save folder" if not found else f"{len(found)} Steam64 save folders"
        raise RuntimeError(
            f"cannot find the Brotato save folder: {what} (17-digit name) under {root}; "
            f"set {ENV_PREFIX}SAVE_DIR to the folder or {ENV_PREFIX}STEAM_ID to its name"
        )

    @cached_property
    def settings_json(self) -> Path:
        if self.settings_json_override is not None:
            return self.settings_json_override
        return self.save_dir / "settings.json"


def load(env: Mapping[str, str] | None = None) -> Paths:
    e: Mapping[str, str] = os.environ if env is None else env

    def ov(name: str, default: Path) -> Path:
        v = e.get(ENV_PREFIX + name.upper())
        return Path(v) if v else default

    def opt(name: str) -> Path | None:
        v = e.get(ENV_PREFIX + name.upper())
        return Path(v) if v else None

    appdata = e.get("APPDATA") or os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set (in the passed mapping or os.environ)")
    brotato_appdata = Path(appdata) / "Brotato"

    game_dir = ov("game_dir", Path(DEFAULT_GAME_DIR))
    pck = ov("pck", game_dir / "Brotato.pck")
    dlc_pck = ov("dlc_pck", game_dir / DLC_PCK_NAME)

    mod_user_dir = ov("mod_user_dir", brotato_appdata / "brotato-bot")
    project_root = ov("project_root", Path(__file__).resolve().parent.parent)
    knowledge_dir = ov("knowledge_dir", project_root / "knowledge")

    return Paths(
        game_dir=game_dir,
        pck=pck,
        dlc_pck=dlc_pck,
        mod_user_dir=mod_user_dir,
        plan_json=ov("plan_json", mod_user_dir / "plan.json"),
        config_json=ov("config_json", mod_user_dir / "config.json"),
        runs_in=ov("runs_in", mod_user_dir / "runs"),
        state_dir=ov("state_dir", mod_user_dir / "state"),
        requests_dir=ov("requests_dir", mod_user_dir / "requests"),
        responses_dir=ov("responses_dir", mod_user_dir / "responses"),
        project_root=project_root,
        data_dir=ov("data_dir", project_root / "data"),
        knowledge_dir=knowledge_dir,
        knowledge_cache=ov("knowledge_cache", knowledge_dir / "cache"),
        runs_out=ov("runs_out", project_root / "runs"),
        decisions_dir=ov("decisions_dir", project_root / "decisions"),
        proposals_dir=ov("proposals_dir", project_root / "proposals"),
        advice_dir=ov("advice_dir", project_root / "advice"),
        brotato_appdata=brotato_appdata,
        save_dir_override=opt("save_dir"),
        steam_id=e.get(ENV_PREFIX + "STEAM_ID") or None,
        settings_json_override=opt("settings_json"),
    )
