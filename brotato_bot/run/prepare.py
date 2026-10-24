"""Write the mod's inputs for the next bot run: ``plan.json``, ``target_challenge`` and the
launch token ``launch.json``.

``plan.json`` also carries ``danger`` and ``starting_weapon`` (a dataset weapon id or
``any``) next to ``target_challenge``. ``launch.json`` (beside ``plan.json``) is the one-shot
launch contract the mod consumes and deletes when it starts a run: ``token``,
``character_id``, ``starting_weapon``, ``danger``, ``target_challenge``, ``created_at``.
The owner still loads the bot profile by hand; the mod refuses on any other profile.

``settings.json`` (in the save dir) holds ``current_profile_id`` at the top level and
``pause_on_focus_lost`` under ``settings``; ``save_v3_0.json`` does not hold the profile id.
The mod reads ``config.json`` once at game start but re-reads ``plan.json`` on change.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brotato_bot.fsutil import atomic_write_json, read_json
from brotato_bot.paths import Paths

REQUIRED_PLAN_KEYS = ("plan_id", "character_id", "plan")
DEFAULT_BOT_PROFILE_ID = 1
LAUNCH_NAME = "launch.json"


def validate_plan(plan: Any) -> None:
    """Raise ValueError unless ``plan`` has string ``plan_id``/``character_id`` and an
    object ``plan`` (the mod's own required keys, runbook 3.5)."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")  # noqa: TRY004
    missing = [k for k in REQUIRED_PLAN_KEYS if k not in plan]
    if missing:
        raise ValueError(f"plan is missing {', '.join(missing)}")
    for k in ("plan_id", "character_id"):
        if not isinstance(plan[k], str) or not plan[k]:
            raise ValueError(f"plan {k} must be a non-empty string")
    if not isinstance(plan["plan"], dict):
        raise ValueError("plan.plan must be an object")  # noqa: TRY004
    tc = plan.get("target_challenge", "")
    if not isinstance(tc, str):
        raise ValueError("plan target_challenge must be a string")  # noqa: TRY004
    danger = plan.get("danger", 0)
    if isinstance(danger, bool) or not isinstance(danger, int):
        raise ValueError("plan danger must be an integer")  # noqa: TRY004
    weapon = plan.get("starting_weapon", "any")
    if not isinstance(weapon, str) or not weapon:
        raise ValueError("plan starting_weapon must be a non-empty string")
    sets = plan["plan"].get("prefer_sets", {})
    if not isinstance(sets, dict) or any(
        isinstance(v, bool) or not isinstance(v, int | float) for v in sets.values()
    ):
        raise ValueError("plan prefer_sets must map set ids to numbers")


def _read_object(path: Path) -> dict | None:
    """The JSON object at path, None when the file is absent; ValueError when unusable."""
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")  # noqa: TRY004
    return data


def bot_profile_id(config: dict) -> int:
    """The bot's profile from the mod's ``config.json`` object: ``bot_profile_id``, default
    1. As in the mod, a value below 1 counts as 1 (profile 0 is the owner's own)."""
    pid = config.get("bot_profile_id", DEFAULT_BOT_PROFILE_ID)
    # BotConfig.load_from: any finite number is truncated to int; else the default.
    if isinstance(pid, bool) or not isinstance(pid, int | float):
        return DEFAULT_BOT_PROFILE_ID
    if isinstance(pid, float) and not math.isfinite(pid):
        return DEFAULT_BOT_PROFILE_ID
    return max(int(pid), DEFAULT_BOT_PROFILE_ID)


def settings_warnings(settings_path: Path, bot_profile_id: int) -> list[str]:
    try:
        settings = _read_object(settings_path)
    except ValueError as exc:
        return [f"{exc}; profile and focus checks skipped"]
    if settings is None:
        return [f"no settings.json at {settings_path}; profile and focus checks skipped"]
    out: list[str] = []
    inner = settings.get("settings")
    pause = inner.get("pause_on_focus_lost") if isinstance(inner, dict) else None
    if pause is None:
        pause = settings.get("pause_on_focus_lost")
    if pause is True:
        out.append("pause_on_focus_lost is true")
    pid = settings.get("current_profile_id")
    if isinstance(pid, int) and pid != bot_profile_id:
        out.append(f"current_profile_id is {pid}")
    return out


def launch_path(paths: Paths) -> Path:
    return paths.plan_json.with_name(LAUNCH_NAME)


def launch_contract(plan: dict, label: str, now: datetime | None = None) -> dict:
    """The ``launch.json`` object for ``plan``; ``label`` (the proposal file stem or the
    plan_id) prefixes the token, which carries the UTC creation time."""
    now = now or datetime.now(UTC)
    return {
        "token": f"{label}-{now:%Y%m%dT%H%M%SZ}",
        "character_id": plan["character_id"],
        "starting_weapon": plan.get("starting_weapon", "any"),
        "danger": plan.get("danger", 0),
        "target_challenge": plan.get("target_challenge", ""),
        "created_at": now.isoformat(timespec="seconds"),
    }


def prepare(
    plan: dict, target: str | None, paths: Paths, launch_label: str | None = None
) -> list[str]:
    """Write ``plan.json`` and merge ``target_challenge`` (``target`` or ``""``) into
    ``config.json``, keeping its other keys. With ``launch_label`` also write ``launch.json``
    (overwriting a stale one); without it a stale ``launch.json`` is removed, so an old token
    never starts a run for a plan it was not written with. Returns warnings."""
    validate_plan(plan)
    config = _read_object(paths.config_json) or {}
    old_target = config.get("target_challenge", "")
    new_target = target or ""

    warnings = settings_warnings(paths.settings_json, bot_profile_id(config))

    plan_target = plan.get("target_challenge", "")
    if plan_target and plan_target != new_target:
        warnings.append(
            f"plan.json target_challenge {plan_target!r} overrides config's {new_target!r}"
        )
    if old_target != new_target:
        warnings.append("config.json changed: restart Brotato, the mod reads it once at start")

    atomic_write_json(paths.plan_json, plan)
    if launch_label is not None:
        atomic_write_json(launch_path(paths), launch_contract(plan, launch_label))
    else:
        launch_path(paths).unlink(missing_ok=True)
    config["target_challenge"] = new_target
    atomic_write_json(paths.config_json, config)
    return warnings
