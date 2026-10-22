# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Build Brotato achievement (challenge) records from ChallengeData .tres + loc CSV.

Achievement text ships pre-rendered per locale in
extracted/tools/output/achievementLocalizations.csv (the game's own Steam
achievement localization export) rather than needing template substitution
against the generic translations.csv the other builders use. That CSV is also
the *filter*, not just a text source: challenge_service.gd reuses the same
ChallengeData resource for a handful of internal item/character unlocks
(chal_evil_hat, chal_doc_moth, chal_wounded, chal_beast_master,
unlock_difficulty_1..6) that were never registered as Steam achievements and
so never made it into the export — merge_achievement_records() drops any
.tres-derived record whose id isn't in the loc CSV.
"""

from __future__ import annotations

import csv
import io
import re

from brotato_bot.dataset.spud.builders.discover import (
    CHARACTER_ID_PREFIX,
    ITEM_ID_PREFIX,
    WEAPON_ID_PREFIX,
)
from brotato_bot.dataset.spud.tres import parse_tres

_REWARD_TYPE = {
    0: "ITEM", 1: "WEAPON", 2: "ZONE", 3: "STARTING_WEAPON",
    4: "CONSUMABLE", 5: "UPGRADE", 6: "CHARACTER", 7: "DIFFICULTY", 8: "SYSTEM",
}

# Reward .tres path -> domain-prefixed id, sourced from the same
# CHARACTER_ID_PREFIX/WEAPON_ID_PREFIX/ITEM_ID_PREFIX constants
# discover.py's find_character_dirs/find_weapon_dirs/find_item_dirs assign,
# so the two can't drift out of sync. Keyed off the path shape rather than
# reward_type so STARTING_WEAPON resolves the same as WEAPON without a
# special case. Only these three occur among real achievement rewards
# (verified against the extracted challenge data) — no consumable/upgrade
# achievement reward has ever shipped.
_REWARD_PATH_PATTERNS = [
    (re.compile(r"items/characters/([^/]+)/"), CHARACTER_ID_PREFIX),
    (re.compile(r"weapons/(?:melee|ranged)/([^/]+)/"), WEAPON_ID_PREFIX),
    (re.compile(r"items/all/([^/]+)/"), ITEM_ID_PREFIX),
]

_LOC_FIELDS = {
    "lockedTitle": "locked_title",
    "lockedDescription": "locked_description",
    "unlockedTitle": "unlocked_title",
    "unlockedDescription": "unlocked_description",
    "flavorText": "flavor_text",
}


def _resolve_reward_id(path: str | None) -> str | None:
    if not path:
        return None
    for pattern, prefix in _REWARD_PATH_PATTERNS:
        m = pattern.search(path)
        if m:
            return f"{prefix}{m.group(1)}"
    return None


def build_achievement_record(chal_text: str) -> dict:
    """Parse one challenges/*.tres file into an achievement record.

    Localization text is attached later by merge_achievement_records(), which
    is also what filters out non-achievement ChallengeData reuses.
    """
    doc = parse_tres(chal_text)
    d = doc.resource

    reward_type_num = d.get("reward_type", 0)
    reward_type = _REWARD_TYPE.get(
        int(reward_type_num) if isinstance(reward_type_num, (int, float)) else -1)

    reward_ref = d.get("reward")
    reward_path = None
    if isinstance(reward_ref, dict) and "__ext__" in reward_ref:
        reward_path = (doc.ext_resources.get(reward_ref["__ext__"]) or {}).get("path")

    return {
        "id": d.get("my_id", ""),
        "stat": d.get("stat") or None,
        "value": d.get("value", 0),
        "additional_args": d.get("additional_args") or [],
        "reward_type": reward_type,
        "reward_id": _resolve_reward_id(reward_path),
        "has_tres": True,
    }


def parse_achievement_localizations_csv(text: str) -> dict[str, dict[str, dict[str, str]]]:
    """Return {achievement_id: {locale: {locked_title, locked_description, unlocked_title, unlocked_description, flavor_text}}}."""
    reader = csv.DictReader(io.StringIO(text))
    out: dict[str, dict[str, dict[str, str]]] = {}
    for row in reader:
        chal_id, locale = row.get("name"), row.get("locale")
        if not chal_id or not locale:
            continue
        out.setdefault(chal_id, {})[locale] = {
            new_key: row.get(old_key, "") for old_key, new_key in _LOC_FIELDS.items()
        }
    return out


def merge_achievement_records(
    tres_records: list[dict], loc_by_id: dict[str, dict[str, dict[str, str]]],
) -> list[dict]:
    """Attach localized text to each tres record and filter to real achievements.

    An id only in loc_by_id (no .tres in this extraction — e.g. DLC content
    not in the unpacked .pck) is kept as a text-only stub with null
    stat/value/reward fields rather than silently dropped.
    """
    remaining = dict(loc_by_id)
    merged: dict[str, dict] = {}

    for rec in tres_records:
        chal_id = rec["id"]
        localized = remaining.pop(chal_id, None)
        if localized is None:
            continue
        merged[chal_id] = {**rec, "localized": localized}

    for chal_id, localized in remaining.items():
        merged[chal_id] = {
            "id": chal_id, "stat": None, "value": None, "additional_args": [],
            "reward_type": None, "reward_id": None,
            "has_tres": False, "localized": localized,
        }

    return [merged[k] for k in sorted(merged)]
