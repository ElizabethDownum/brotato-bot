"""Distill extracted pck game data into ``data/brotato.json``.

Reproduces Spud Coach's ``build_dataset.py`` main flow (upstream commit 9e02315, see
learnings/upstream.md) with two differences: ``game_version`` is passed in (detected
from the pck by ``version.detect_game_version``) instead of read from a decompiled
``recovered/`` tree, and the output is written atomically. Translations come from a
Godot translations CSV (or several, merged in order with later files winning) when
supplied or present under ``extracted``; the pcks ship only binary ``.translation``
resources, so builds straight from the pck fall back to slug-derived names.

Content comes from the base layout and every ``dlcs/<name>/`` tree (see
``discover.ContentSource``). Every record carries ``dlc``: the DLC directory name
(e.g. ``"dlc_1"``) or None for base content, and ``source`` echoes it ("base" or the
DLC name). An id that appears twice (within or across sources) fails the build.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from brotato_bot.dataset.spud import dataset
from brotato_bot.dataset.spud.builders import discover
from brotato_bot.dataset.spud.builders.characters import build_character_record
from brotato_bot.dataset.spud.builders.enemies import build_enemy_record
from brotato_bot.dataset.spud.builders.items import build_item_record
from brotato_bot.dataset.spud.builders.localization import parse_translations_csv
from brotato_bot.dataset.spud.builders.provenance import detect_source
from brotato_bot.dataset.spud.builders.sets import build_set_record
from brotato_bot.dataset.spud.builders.timestamps import format_generated_at
from brotato_bot.dataset.spud.builders.waves import build_wave_record
from brotato_bot.dataset.spud.builders.weapons import build_weapon_record
from brotato_bot.dataset.spud.tres import parse_tres
from brotato_bot.fsutil import atomic_write_json

TRANSLATIONS_CSV = Path("resources") / "translations" / "translations.csv"


def _read(path: str | Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _coverage_report_lines(coverage: dict, unmodeled_by_source: dict) -> list[str]:
    lines: list[str] = []
    for label, key in (
        ("new content trees", "unclaimed_trees"),
        ("new weapon kinds", "unknown_weapon_kinds"),
        ("new/unmodeled zones", "unmodeled_zones"),
    ):
        vals = coverage.get(key) or []
        if vals:
            lines.append(f"  {label}: {', '.join(vals)}")
    for src, keys in (unmodeled_by_source or {}).items():
        if keys:
            shown = ", ".join(keys[:8]) + ("..." if len(keys) > 8 else "")
            lines.append(f"  unmodeled effects [{src}]: {len(keys)} ({shown})")
    return lines


def _stamp_sources(*record_lists: list[dict]) -> None:
    for records in record_lists:
        for rec in records:
            rec["source"] = detect_source(record=rec)


def _load_translations(translations: Path | list[Path] | None, extracted: Path) -> dict[str, str]:
    if translations is None:
        paths = [Path(extracted) / TRANSLATIONS_CSV]
    elif isinstance(translations, (str, Path)):
        paths = [Path(translations)]
    else:
        paths = [Path(t) for t in translations]
    tr: dict[str, str] = {}
    for path in paths:
        if path.is_file():
            # utf-8-sig: GDRE-exported CSVs start with a BOM.
            with open(path, encoding="utf-8-sig") as fh:
                tr.update(parse_translations_csv(fh.read()))
    return tr


def _tag(record: dict, entry: dict) -> dict:
    record["dlc"] = entry.get("dlc")
    return record


def _duplicate_ids(coll: str, records: list[dict], key=lambda r: r["id"]) -> list[str]:
    seen: dict = {}
    problems = []
    for rec in records:
        k = key(rec)
        if k in seen:
            label = k if isinstance(k, str) else k[0]
            problems.append(
                f"duplicate {coll} id {label!r} (sources {seen[k]!r} and {rec.get('dlc')!r})"
            )
        else:
            seen[k] = rec.get("dlc")
    return problems


def _per_source_counts(colls: dict[str, list[dict]]) -> str:
    parts = []
    for name, recs in colls.items():
        counts: dict[str, int] = {}
        for r in recs:
            src = r.get("dlc") or "base"
            counts[src] = counts.get(src, 0) + 1
        parts.append(f"{name} " + "/".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return "; ".join(parts)


def build_dataset(
    extracted: Path,
    out: Path,
    game_version: str,
    *,
    translations: Path | list[Path] | None = None,
    generated_at: str | None = None,
) -> dict:
    """Build, validate and write the dataset; return it. Raises ValueError on invalid data."""
    root = str(extracted)
    if generated_at is None:
        generated_at = format_generated_at(datetime.now(UTC))
    tr = _load_translations(translations, Path(extracted))

    weapons = []
    for entry in discover.find_weapon_dirs(root):
        effect_paths = entry.get("effect_paths", [])
        companion_paths = entry.get("effect_companion_paths", {})
        effect_companion_texts = [
            {field: _read(path) for field, path in companion_paths[p].items()}
            if p in companion_paths
            else None
            for p in effect_paths
        ]
        weapons.append(
            _tag(
                build_weapon_record(
                    _read(entry["stats_path"]),
                    _read(entry["data_path"]),
                    [_read(p) for p in effect_paths],
                    effect_companion_texts,
                    weapon_id=entry["weapon_id"],
                    name=entry["name"],
                    tier=entry["tier"],
                    classes=entry.get("classes", []),
                    tr=tr,
                ),
                entry,
            )
        )

    items = [
        _tag(
            build_item_record(
                _read(e["data_path"]),
                [_read(p) for p in e["effect_paths"]],
                item_id=e["item_id"],
                name=e["name"],
                tr=tr,
            ),
            e,
        )
        for e in discover.find_item_dirs(root)
    ]

    sets = [
        _tag(
            build_set_record(
                _read(e["set_data_path"]),
                {c: _read(p) for c, p in e["count_effect_paths"].items()},
                set_id=e["set_id"],
                name=e["name"],
                tr=tr,
            ),
            e,
        )
        for e in discover.find_set_dirs(root)
    ]
    set_names = {s["id"]: s["display_name"] for s in sets}
    # Keyed by tier-agnostic weapon id (a starting-weapon pool is always tier 1).
    weapons_by_id = {w["id"]: w for w in weapons}

    characters = []
    for e in discover.find_character_dirs(root):
        data_text = _read(e["data_path"])
        res = parse_tres(data_text).resource
        characters.append(
            _tag(
                build_character_record(
                    data_text,
                    [_read(p) for p in e["effect_paths"]],
                    char_id=e["char_id"],
                    name=e["name"],
                    wanted_tags=res.get("wanted_tags", []) or [],
                    banned_item_groups=res.get("banned_item_groups", []) or [],
                    tr=tr,
                    set_names=set_names,
                    weapons_by_id=weapons_by_id,
                ),
                e,
            )
        )

    enemies = []
    for e in discover.find_enemy_dirs(root):
        scene_text = _read(e["scene_path"]) if e.get("scene_path") else None
        enemies.append(
            _tag(
                build_enemy_record(
                    _read(e["stats_path"]),
                    scene_text,
                    enemy_id=e["enemy_id"],
                    name=e["name"],
                    tr=tr,
                ),
                e,
            )
        )

    zone_1_waves = []
    enemy_ids_in_waves: set[str] = set()
    for wv in discover.find_zone_waves(root):
        group_texts = [_read(p) for p in wv["group_paths"]]
        unit_texts_by_group = {
            gkey: [_read(p) for p in paths] for gkey, paths in wv["unit_paths_by_group"].items()
        }
        rec = build_wave_record(
            _read(wv["wave_path"]), group_texts, unit_texts_by_group, wave=wv["wave"]
        )
        for g in rec["groups"]:
            if g.get("enemy_id"):
                enemy_ids_in_waves.add(g["enemy_id"])
        zone_1_waves.append(rec)

    # appears_in: "normal" for any enemy referenced by a numbered wave
    for e in enemies:
        e["appears_in"] = ["normal"] if e["id"] in enemy_ids_in_waves else []

    _stamp_sources(weapons, items, characters, sets, enemies, zone_1_waves)

    ds = dataset.assemble_dataset(
        game_version=game_version,
        generated_at=generated_at,
        weapons=weapons,
        items=items,
        characters=characters,
        sets=sets,
        enemies=enemies,
        zone_1_waves=zone_1_waves,
    )

    problems = dataset.validate_dataset(ds)
    # Weapons repeat their id once per tier; every other collection is one record per id.
    problems += _duplicate_ids("weapon", weapons, key=lambda r: (r["id"], r["tier"]))
    for coll, recs in (
        ("item", items),
        ("character", characters),
        ("set", sets),
        ("enemy", enemies),
    ):
        problems += _duplicate_ids(coll, recs)
    if problems:
        raise ValueError("Dataset validation failed:\n" + "\n".join(f"  - {p}" for p in problems))

    report = _coverage_report_lines(
        discover.coverage_report(root), dataset.aggregate_unmodeled_effects(ds)
    )
    if report:
        print("Coverage / unmodeled-content report:", file=sys.stderr)
        for line in report:
            print(line, file=sys.stderr)

    atomic_write_json(Path(out), ds)
    print(
        f"Wrote {out}: {len(weapons)} weapon records, {len(items)} item records, "
        f"{len(characters)} character records, {len(sets)} set records, "
        f"{len(enemies)} enemy records, {len(zone_1_waves)} zone_1 wave records "
        f"({'localized' if tr else 'NO translations found - slug names only'})"
    )
    print(
        "Per source: "
        + _per_source_counts(
            {
                "weapons": weapons,
                "items": items,
                "characters": characters,
                "sets": sets,
                "enemies": enemies,
            }
        )
    )
    return ds
