# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

from brotato_bot.dataset.spud.builders.localization import resolve_text
from brotato_bot.dataset.spud.tres import parse_tres

_GAIN_KEYS = {"effect_increase_stat_gains", "effect_reduce_stat_gains"}


def _weapon_id_from_res_path(path: str) -> str:
    """`res://weapons/<type>/<slug>/<tier>/<slug>_data.tres` -> `weapon_<slug>`.

    The slug directory is the weapon's identity; the tier directory below it is
    not, because a starting-weapon pool always offers tier 1.
    """
    parts = [p for p in str(path).split("/") if p]
    return f"weapon_{parts[-3]}" if len(parts) >= 3 else ""


def _starting_weapon_pool(doc, weapons_by_id: dict[str, dict]) -> list[str]:
    """Resolve `starting_weapons` ext-resource refs to weapon display names.

    This is the run-start SELECTION POOL the weapon-selection menu offers
    (ui/menus/run/weapon_selection.gd:92 -> RewardType.STARTING_WEAPON), not a
    fixed starting weapon: most characters offer a dozen or more, and two
    (Beast Master, Bull) offer none. Ordering mirrors the game's own
    get_ordered_starting_weapons (singletons/item_service.gd:1043) — every
    melee weapon first, then every ranged one.
    """
    if not weapons_by_id:
        return []
    melee: list[str] = []
    ranged: list[str] = []
    seen: set[str] = set()
    for ref in doc.resource.get("starting_weapons") or []:
        if not (isinstance(ref, dict) and "__ext__" in ref):
            continue
        path = (doc.ext_resources.get(ref["__ext__"]) or {}).get("path") or ""
        weapon = weapons_by_id.get(_weapon_id_from_res_path(path))
        if weapon is None:
            continue
        # display_name is the localized in-game text; `name` is only the
        # slug-titlecased fallback, and the two diverge for 7 weapons
        # (Smg -> SMG, Cactus Mace -> Cacti Club, ...). A client filtering on a
        # starting weapon will use the name the game shows.
        label = weapon.get("display_name") or weapon["name"]
        if label in seen:
            continue
        seen.add(label)
        bucket = melee if weapon.get("weapon_type") == "melee" else ranged
        bucket.append(label)
    return melee + ranged


def _set_name(set_id: str, set_names: dict[str, str]) -> str:
    name = set_names.get(set_id)
    if name:
        return name
    slug = set_id[len("set_"):] if set_id.startswith("set_") else set_id
    return slug.replace("_", " ").title()


def build_character_record(data_text: str, effect_texts: list[str], *, char_id: str,
                          name: str, wanted_tags: list[str],
                          banned_item_groups: list[str],
                          tr: dict[str, str] | None = None,
                          set_names: dict[str, str] | None = None,
                          weapons_by_id: dict[str, dict] | None = None) -> dict:
    doc = parse_tres(data_text)
    d = doc.resource
    flat_bonuses: list[dict] = []
    gain_modifiers: list[dict] = []
    special_effects: list[str] = []
    class_bonuses: list[dict] = []
    set_names = set_names or {}

    for text in effect_texts:
        r = parse_tres(text).resource
        key = str(r.get("key", ""))
        set_id = r.get("set_id")
        if key in _GAIN_KEYS:
            mods = r.get("stats_modified", []) or []
            stat = mods[0] if mods else None
            if stat is not None:
                gain_modifiers.append({"stat": stat, "pct": r.get("value", 0)})
        # A non-empty set_id is the sole discriminator for a ClassBonusEffect
        # (its .tres always carries set_id + stat_name). The effect key varies
        # in case across characters (effect_weapon_class_bonus /
        # EFFECT_WEAPON_CLASS_BONUS), so we deliberately do NOT gate on it.
        elif set_id:
            class_bonuses.append({
                "set_id": str(set_id),
                "set_name": _set_name(str(set_id), set_names),
                "stat": str(r.get("stat_name", "")),
                "stat_displayed": str(r.get("stat_displayed_name", "")),
                "value": r.get("value", 0),
            })
        elif key.startswith("stat_"):
            flat_bonuses.append({"stat": key, "value": r.get("value", 0)})
        else:
            if not key.startswith("weapon_"):
                special_effects.append(key)

    return {
        "id": char_id,
        "name": name,
        "display_name": resolve_text(tr, d.get("name"), name),
        "description": resolve_text(tr, d.get("description")),
        "wanted_tags": wanted_tags,
        "banned_item_groups": banned_item_groups,
        "starting_weapon_pool": _starting_weapon_pool(doc, weapons_by_id or {}),
        "flat_bonuses": flat_bonuses,
        "gain_modifiers": gain_modifiers,
        "special_effects": special_effects,
        "class_bonuses": class_bonuses,
    }
