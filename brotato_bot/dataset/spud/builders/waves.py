# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

import os

from brotato_bot.dataset.spud.tres import parse_tres


def enemy_id_from_unit_scene(scene_name: str) -> str:
    return os.path.basename(scene_name).removesuffix(".tscn")


def _int(d: dict, key: str, default: int = 0) -> int:
    v = d.get(key)
    return int(v) if isinstance(v, (int, float)) else default


def _unit_enemy_id(unit_text: str) -> str:
    r = parse_tres(unit_text).resource
    name = r.get("unit_scene_name")
    if isinstance(name, str) and name:
        return enemy_id_from_unit_scene(name)
    # fall back to the unit_scene ExtResource path basename
    ref = r.get("unit_scene")
    if isinstance(ref, dict) and "__ext__" in ref:
        ext = parse_tres(unit_text).ext_resources.get(ref["__ext__"]) or {}
        return enemy_id_from_unit_scene(str(ext.get("path", "")))
    return ""


def _group_record(group_text: str, unit_texts: list[str]) -> list[dict]:
    g = parse_tres(group_text).resource
    common = {
        "first_spawn_s": _int(g, "spawn_timing", 1),
        "repeats": _int(g, "repeating", 0),
        "repeat_interval": _int(g, "repeating_interval", 0),
        "spawn_chance": g.get("spawn_chance", 1.0),
        "min_danger": _int(g, "min_difficulty", 0),
        "max_danger": _int(g, "max_difficulty", 9999),
        "is_horde": bool(g.get("is_horde", False)),
        "is_boss": bool(g.get("is_boss", False)),
        "is_loot": bool(g.get("is_loot", False)),
    }
    out = []
    for unit_text in unit_texts:
        u = parse_tres(unit_text).resource
        out.append({
            "enemy_id": _unit_enemy_id(unit_text),
            "base_count": [_int(u, "min_number", 1), _int(u, "max_number", 1)],
            **common,
        })
    return out


def build_wave_record(wave_text: str, group_texts: list[str],
                      unit_texts_by_group: dict[str, list[str]], *, wave: int) -> dict:
    w = parse_tres(wave_text).resource
    groups: list[dict] = []
    # Positional pairing: group_texts[i] corresponds to the i-th entry in
    # unit_texts_by_group. find_zone_waves builds both in a single pass (same
    # order), so this 1:1 index alignment holds. (Relies on that construction
    # order — it is not a basename-keyed lookup.)
    keys = list(unit_texts_by_group.keys())
    for i, gtext in enumerate(group_texts):
        units = unit_texts_by_group.get(keys[i]) if i < len(keys) else []
        groups.extend(_group_record(gtext, units or []))
    return {
        "wave": wave,
        "wave_duration": _int(w, "wave_duration", 60),
        "max_enemies": _int(w, "max_enemies", 100),
        "groups": groups,
    }
