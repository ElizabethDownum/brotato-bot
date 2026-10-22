# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

import glob
import os
import re

from brotato_bot.dataset.spud.tres import parse_tres

# Domain id prefixes assigned below and reused by
# achievements.py::_resolve_reward_id — keep both in sync with these
# constants rather than duplicating the literals.
CHARACTER_ID_PREFIX = "character_"
WEAPON_ID_PREFIX = "weapon_"
ITEM_ID_PREFIX = "item_"

# Baseline snapshot of Brotato 1.1.15.4's extracted/ layout (verified against
# the current extraction). coverage_report() flags anything NOT in these sets —
# empty on the base game, non-empty when a game/DLC update adds a new content
# tree, weapon kind, or zone. Extend a set only when its new content has been
# triaged into the build.
_ACCOUNTED_TOP_LEVEL = frozenset({
    "addons", "challenges", "effect_behaviors", "effects", "entities", "global",
    "items", "overlap", "particles", "projectiles", "resources", "singletons",
    "tools", "ui", "visual_effects", "weapons", "zones",
})
_ACCOUNTED_WEAPON_SUBDIRS = frozenset({
    "melee", "ranged", "melee_sounds", "shooting_behaviors", "weapon_stats",
})
# zone_1 (ZONE_CRASH_ZONE, unlocked_by_default=true, ~336 .tres) is the modeled
# base zone. zone_2 (ZONE_LAKE) and zone_3 (ZONE_VOLCANIC_GROUNDS) ship in the
# base 1.1.15.4 PCK as inert stubs — 5 .tres each, unlocked_by_default=false, a
# single placeholder wave — i.e. pre-staged Abyssal Terrors DLC zones, disabled.
# They are accounted for so the base build stays clean; installing the DLC fills
# them in (a modeling task, not a coverage drop). backgrounds/common are non-wave
# assets. Only a genuinely NEW zone dir surfaces here.
_ACCOUNTED_ZONE_SUBDIRS = frozenset({
    "zone_1", "zone_2", "zone_3", "backgrounds", "common",
})


def _immediate_subdirs(path: str) -> set[str]:
    if not os.path.isdir(path):
        return set()
    # Dot-prefixed dirs (Godot's `.import` cache, `.godot`, etc.) are tooling
    # artifacts, never Brotato content, in any of the three trees this scans.
    return {n for n in os.listdir(path)
            if not n.startswith(".") and os.path.isdir(os.path.join(path, n))}


def coverage_report(extracted_root: str) -> dict[str, list[str]]:
    """New content trees / weapon kinds / zones not in the 1.1.15.4 baseline.

    Empty on the base game. A DLC (or major patch) that introduces a new
    top-level content tree, a new weapon kind, or a new zone surfaces it here so
    the build can report — and, under --strict, refuse to ship — un-triaged
    content instead of silently dropping it.
    """
    return {
        "unclaimed_trees": sorted(
            _immediate_subdirs(extracted_root) - _ACCOUNTED_TOP_LEVEL),
        "unknown_weapon_kinds": sorted(
            _immediate_subdirs(os.path.join(extracted_root, "weapons"))
            - _ACCOUNTED_WEAPON_SUBDIRS),
        "unmodeled_zones": sorted(
            _immediate_subdirs(os.path.join(extracted_root, "zones"))
            - _ACCOUNTED_ZONE_SUBDIRS),
    }


def _res_url_to_path(extracted_root: str, res_url: str | None) -> str | None:
    if res_url and res_url.startswith("res://"):
        return os.path.join(extracted_root, res_url[len("res://"):])
    return None


def _resolve_weapon_refs(extracted_root: str, data_path: str) -> tuple[list[str], list[str]]:
    """Follow a weapon data .tres's `effects` and `sets` ext_resource references.

    Returns (effect_paths, class_names). The weapon's data .tres lists its effects
    and set memberships as ExtResource(id) entries; the parser records each id's
    file path in the ext_resource table. We resolve those the same way the item
    and character builders already resolve their effect files.
    """
    with open(data_path, encoding="utf-8") as fh:
        doc = parse_tres(fh.read())
    ext, res = doc.ext_resources, doc.resource

    def ref_ids(field: str) -> list[int]:
        return [e["__ext__"] for e in (res.get(field) or [])
                if isinstance(e, dict) and "__ext__" in e]

    effect_paths: list[str] = []
    for rid in ref_ids("effects"):
        path = _res_url_to_path(extracted_root, (ext.get(rid) or {}).get("path"))
        if path and os.path.isfile(path):
            effect_paths.append(path)

    classes: list[str] = []
    for rid in ref_ids("sets"):
        path = (ext.get(rid) or {}).get("path") or ""
        if "/sets/" in path:
            cls = path.split("/sets/", 1)[1].split("/", 1)[0]
            name = cls.replace("_", " ").title()
            if name not in classes:
                classes.append(name)
    return effect_paths, classes


# Effect fields whose value is an ext_resource reference to a companion .tres
# carrying the real gameplay numbers. Resolution follows the reference URL —
# never a filename glob: three distinct companion naming conventions ship
# (`*_burning_data`, `*_projectile`, `*_proj_stats`), and structure stats live
# outside the weapon dir entirely (items/all/landmines/). A filename-based
# approach already caused the *_data.tres glob collision fixed in 25f8ca2.
_COMPANION_FIELDS = ("burning_data", "weapon_stats", "stats")


def _resolve_effect_companions(extracted_root: str, effect_paths: list[str]) -> dict[str, dict[str, str]]:
    """Resolve each effect's companion-resource references, if any.

    Returns effect path -> {field name: companion path}, omitting effects
    that reference no companion.
    """
    result: dict[str, dict[str, str]] = {}
    for effect_path in effect_paths:
        with open(effect_path, encoding="utf-8") as fh:
            doc = parse_tres(fh.read())
        companions: dict[str, str] = {}
        for field in _COMPANION_FIELDS:
            ref = doc.resource.get(field)
            if isinstance(ref, dict) and "__ext__" in ref:
                ext = doc.ext_resources.get(ref["__ext__"]) or {}
                path = _res_url_to_path(extracted_root, ext.get("path"))
                if path and os.path.isfile(path):
                    companions[field] = path
        if companions:
            result[effect_path] = companions
    return result


def find_weapon_dirs(extracted_root: str) -> list[dict]:
    results = []
    for kind in ("ranged", "melee"):
        pattern = os.path.join(extracted_root, "weapons", kind, "*", "*")
        for tier_dir in sorted(glob.glob(pattern)):
            if not os.path.isdir(tier_dir):
                continue
            tier_name = os.path.basename(tier_dir)
            if not tier_name.isdigit():
                continue
            weapon_folder = os.path.basename(os.path.dirname(tier_dir))
            # The weapon's own stats file always follows one of two exact
            # naming forms: "{folder}_{tier}_stats.tres" (most tiers) or the
            # bare "{folder}_stats.tres" (observed for some tier-1 dirs, e.g.
            # torch/1/, pruner/1/). Companion stats files -- a projectile's
            # "_proj_stats.tres" (Sniper Gun, fixed by d06e78c), a turret
            # companion's "_garden_stats.tres" (Pruner tiers 2-4), and future
            # variants we haven't seen yet -- always insert an extra word
            # before "_stats.tres", so they never match either exact form.
            # This is a whitelist, not a blocklist: it generalizes to new
            # companion suffixes instead of requiring a new exclusion each
            # time one is discovered.
            stats = [
                p for p in (
                    os.path.join(tier_dir, f"{weapon_folder}_{tier_name}_stats.tres"),
                    os.path.join(tier_dir, f"{weapon_folder}_stats.tres"),
                )
                if os.path.isfile(p)
            ]
            data = sorted(
                p for p in glob.glob(os.path.join(tier_dir, "*_data.tres"))
                if not os.path.basename(p).endswith("_burning_data.tres"))
            if not stats or not data:
                continue
            effect_paths, classes = _resolve_weapon_refs(extracted_root, data[0])
            companion_paths = _resolve_effect_companions(extracted_root, effect_paths)
            results.append({
                "weapon_id": f"{WEAPON_ID_PREFIX}{weapon_folder}",
                "name": weapon_folder.replace("_", " ").title(),
                "tier": int(tier_name),
                "stats_path": stats[0],
                "data_path": data[0],
                "effect_paths": effect_paths,
                "effect_companion_paths": companion_paths,
                "classes": classes,
            })
    return results


def _title(folder: str) -> str:
    return folder.replace("_", " ").title()


def _find_item_data_path(dir_path: str, folder: str) -> str | None:
    """Locate an item dir's main data file.

    Most items name it "{folder}_data.tres", but pets (and a few others,
    e.g. evil_hat) ship it as a bare "{folder}.tres" instead. Identify the
    real data file by its script reference (items/global/item_data.gd)
    rather than assuming a fixed filename.
    """
    std = os.path.join(dir_path, f"{folder}_data.tres")
    if os.path.isfile(std):
        return std
    for path in sorted(glob.glob(os.path.join(dir_path, "*.tres"))):
        with open(path, encoding="utf-8") as fh:
            doc = parse_tres(fh.read())
        script_ref = doc.resource.get("script")
        if isinstance(script_ref, dict) and "__ext__" in script_ref:
            ext = doc.ext_resources.get(script_ref["__ext__"]) or {}
            if str(ext.get("path", "")).endswith("item_data.gd"):
                return path
    return None


def find_item_dirs(extracted_root: str) -> list[dict]:
    results = []
    for d in sorted(glob.glob(os.path.join(extracted_root, "items", "all", "*"))):
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(d)
        data = _find_item_data_path(d, folder)
        if not data:
            continue
        # The effect files share the data file's own prefix, which isn't
        # always the folder name (e.g. eyes_surgery/'s files are prefixed
        # "eye_surgery").
        data_name = os.path.basename(data)
        prefix = data_name[: -len("_data.tres")] if data_name.endswith("_data.tres") else data_name[: -len(".tres")]
        effects = sorted(glob.glob(os.path.join(d, f"{prefix}_effect_*.tres")))
        results.append({
            "item_id": f"{ITEM_ID_PREFIX}{folder}", "name": _title(folder),
            "data_path": data, "effect_paths": effects,
        })
    return results


def find_character_dirs(extracted_root: str) -> list[dict]:
    results = []
    for d in sorted(glob.glob(os.path.join(extracted_root, "items", "characters", "*"))):
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(d)
        data = os.path.join(d, f"{folder}_data.tres")
        if not os.path.isfile(data):
            continue
        effects = sorted(glob.glob(os.path.join(d, f"{folder}_effect_*.tres")))
        results.append({
            "char_id": f"{CHARACTER_ID_PREFIX}{folder}", "name": _title(folder),
            "data_path": data, "effect_paths": effects,
        })
    return results


def find_set_dirs(extracted_root: str) -> list[dict]:
    results = []
    for d in sorted(glob.glob(os.path.join(extracted_root, "items", "sets", "*"))):
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(d)
        set_data = os.path.join(d, f"{folder}_set_data.tres")
        if not os.path.isfile(set_data):
            continue
        count_effects = {}
        for sub in sorted(glob.glob(os.path.join(d, "*"))):
            b = os.path.basename(sub)
            if os.path.isdir(sub) and b.isdigit():
                eff = glob.glob(os.path.join(sub, f"set_{b}_effect_1.tres"))
                if eff:
                    count_effects[int(b)] = eff[0]
        results.append({
            "set_id": f"set_{folder}", "name": _title(folder),
            "set_data_path": set_data, "count_effect_paths": count_effects,
        })
    return results


def find_challenge_paths(extracted_root: str) -> list[str]:
    """Top-level challenges/*.tres — one per ChallengeData (achievement or
    internal unlock; achievements.merge_achievement_records filters the latter
    out). Excludes challenges/global/, which holds the .gd schema, not data."""
    return sorted(glob.glob(os.path.join(extracted_root, "challenges", "*.tres")))


def _enemy_stats_path(dir_path: str, folder: str) -> str | None:
    """Locate an enemy dir's stats file.

    Most enemies name it "{folder}_stats.tres", but at least one (evil_mob)
    ships it as a bare "{folder}.tres" instead. Fall back to the bare name
    only when its script reference is a stats resource (ends in stats.gd),
    mirroring _find_item_data_path's fallback pattern above.
    """
    stats = sorted(glob.glob(os.path.join(dir_path, "*_stats.tres")))
    if stats:
        return stats[0]
    bare = os.path.join(dir_path, f"{folder}.tres")
    if os.path.isfile(bare):
        with open(bare, encoding="utf-8") as fh:
            doc = parse_tres(fh.read())
        ref = doc.resource.get("script")
        if isinstance(ref, dict) and "__ext__" in ref:
            ext = doc.ext_resources.get(ref["__ext__"]) or {}
            if str(ext.get("path", "")).endswith("stats.gd"):
                return bare
    return None


def find_enemy_dirs(extracted_root: str) -> list[dict]:
    results = []
    base = os.path.join(extracted_root, "entities", "units", "enemies")
    for d in sorted(glob.glob(os.path.join(base, "*"))):
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(d)
        stats_path = _enemy_stats_path(d, folder)
        if not stats_path:
            continue
        scene = os.path.join(d, f"{folder}.tscn")
        results.append({
            "enemy_id": folder,
            "name": _title(folder),
            "folder": folder,
            "stats_path": stats_path,
            "scene_path": scene if os.path.isfile(scene) else None,
        })
    return results


_WAVE_FILE_RE = re.compile(r"wave_(\d+)\.tres$")


def find_zone_waves(extracted_root: str) -> list[dict]:
    """Numbered zone_1 waves 1-20, resolving each wave's groups and their units.

    Excludes the "021 (test)" dir (wave number > 20). Each result carries the
    wave text path plus, per group, the group .tres path and its unit .tres
    paths, resolved through the ext_resource tables.
    """
    base = os.path.join(extracted_root, "zones", "zone_1")
    results = []
    for wave_path in sorted(glob.glob(os.path.join(base, "*", "wave_*.tres"))):
        m = _WAVE_FILE_RE.search(os.path.basename(wave_path))
        if not m:
            continue
        wave_no = int(m.group(1))
        if not (1 <= wave_no <= 20):
            continue
        with open(wave_path, encoding="utf-8") as fh:
            wdoc = parse_tres(fh.read())
        group_paths, unit_paths_by_group = [], {}
        for entry in wdoc.resource.get("groups_data", []) or []:
            if not (isinstance(entry, dict) and "__ext__" in entry):
                continue
            gpath = _res_url_to_path(extracted_root,
                                     (wdoc.ext_resources.get(entry["__ext__"]) or {}).get("path"))
            if not (gpath and os.path.isfile(gpath)):
                continue
            group_paths.append(gpath)
            gkey = os.path.basename(gpath)
            with open(gpath, encoding="utf-8") as fh:
                gdoc = parse_tres(fh.read())
            units = []
            for uentry in gdoc.resource.get("wave_units_data", []) or []:
                if isinstance(uentry, dict) and "__ext__" in uentry:
                    upath = _res_url_to_path(
                        extracted_root,
                        (gdoc.ext_resources.get(uentry["__ext__"]) or {}).get("path"))
                    if upath and os.path.isfile(upath):
                        units.append(upath)
            unit_paths_by_group[gkey] = units
        results.append({
            "wave": wave_no, "wave_path": wave_path,
            "group_paths": group_paths, "unit_paths_by_group": unit_paths_by_group,
        })
    results.sort(key=lambda r: r["wave"])
    return results
