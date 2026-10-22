# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

import json

from brotato_bot.dataset.spud.builders.mechanics import STAT_MECHANICS

DATASET_VERSION = 8  # was 7 (character `starting_weapon_pool`)

# base_damage and cooldown are calculation-critical: the DPS engine reads them
# unconditionally, so a weapon without them must fail the build, not a query.
_REQUIRED_WEAPON_KEYS = ("id", "name", "tier", "weapon_type", "base_damage", "cooldown")
_WEAPON_TYPES = ("melee", "ranged")


def assemble_dataset(*, game_version: str, generated_at: str, weapons: list,
                     items: list, characters: list, sets: list,
                     enemies: list, zone_1_waves: list) -> dict:
    all_records = [*weapons, *items, *characters, *sets, *enemies, *zone_1_waves]
    content_sources = sorted({r["source"] for r in all_records if "source" in r}) or ["base"]
    return {
        "schema_version": DATASET_VERSION,
        "game_version": game_version,
        "generated_at": generated_at,
        "content_sources": content_sources,
        "stat_mechanics": STAT_MECHANICS,
        "weapons": weapons,
        "items": items,
        "characters": characters,
        "sets": sets,
        "enemies": enemies,
        "zone_1_waves": zone_1_waves,
    }


def validate_dataset(dataset: dict) -> list[str]:
    problems: list[str] = [
        f"missing top-level key: {key}"
        for key in ("schema_version", "game_version", "content_sources", "weapons",
                    "items", "characters", "sets", "enemies", "zone_1_waves")
        if key not in dataset
    ]

    for w in dataset.get("weapons", []):
        wid = w.get("id", "<unknown>")
        problems.extend(f"weapon {wid} missing key: {k}" for k in _REQUIRED_WEAPON_KEYS if k not in w)
        tier = w.get("tier")
        if not isinstance(tier, int) or not (1 <= tier <= 4):
            problems.append(f"weapon {wid} has invalid tier: {tier}")
        wt = w.get("weapon_type")
        if wt is not None and wt not in _WEAPON_TYPES:
            problems.append(f"weapon {wid} has unknown weapon_type: {wt}")

    for it in dataset.get("items", []):
        if not isinstance(it.get("effects"), list):
            problems.append(f"item {it.get('id', '<unknown>')} missing effects list")
        if "id" not in it:
            problems.append(f"item missing id: {it.get('name', '<unknown>')}")
    for ch in dataset.get("characters", []):
        if "id" not in ch:
            problems.append(f"character missing id: {ch.get('name', '<unknown>')}")
        if not isinstance(ch.get("gain_modifiers"), list):
            problems.append(f"character {ch.get('id', '<unknown>')} missing gain_modifiers list")
        if not isinstance(ch.get("class_bonuses"), list):
            problems.append(f"character {ch.get('id', '<unknown>')} missing class_bonuses list")
        # An EMPTY pool is valid data (Beast Master and Bull start weaponless);
        # a missing key is a build regression.
        if not isinstance(ch.get("starting_weapon_pool"), list):
            problems.append(
                f"character {ch.get('id', '<unknown>')} missing starting_weapon_pool list")
    problems.extend(
        f"set {st.get('id', '<unknown>')} missing bonuses list"
        for st in dataset.get("sets", [])
        if not isinstance(st.get("bonuses"), list)
    )

    enemy_ids = {e.get("id") for e in dataset.get("enemies", [])}
    problems.extend(
        f"enemy missing id: {e.get('name', '<unknown>')}"
        for e in dataset.get("enemies", [])
        if "id" not in e
    )
    for w in dataset.get("zone_1_waves", []):
        for g in w.get("groups", []):
            eid = g.get("enemy_id")
            if eid and eid not in enemy_ids:
                problems.append(
                    f"wave {w.get('wave', '?')} references unknown enemy '{eid}'")

    for coll_name in ("weapons", "items", "characters", "sets", "enemies", "zone_1_waves"):
        for rec in dataset.get(coll_name, []):
            if "source" not in rec:
                rid = rec.get("id") or rec.get("name") or rec.get("wave", "<unknown>")
                problems.append(f"{coll_name} record {rid} missing source")

    return problems


def aggregate_unmodeled_effects(dataset: dict) -> dict[str, list[str]]:
    """Map content source -> sorted unique unmodeled effect keys across all
    records. Empty when every effect is modeled or classified (the base-game
    state today). A DLC introducing new effect scripts populates it as the
    modeling worklist, bucketed by origin."""
    by_source: dict[str, set[str]] = {}
    for coll in ("weapons", "items", "characters", "sets", "enemies"):
        for rec in dataset.get(coll, []):
            src = rec.get("source", "base")
            for key in rec.get("unmodeled_effects", []) or []:
                by_source.setdefault(src, set()).add(str(key))
    return {src: sorted(keys) for src, keys in sorted(by_source.items())}


def load_dataset(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"dataset not found at {path}; run build_dataset.py first"
        ) from exc
