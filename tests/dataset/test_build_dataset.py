import json

import pytest

from brotato_bot.dataset.build import build_dataset

_ITEM_DATA = """[gd_resource type="Resource" format=2]
[resource]
tier = 2
value = 80
tags = [ "stat_melee_damage" ]
"""
_ITEM_EFFECT = '[resource]\nkey = "stat_melee_damage"\nvalue = 8\neffect_sign = 3\ntext_key = ""\n'

_WAVE = """[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://zones/wave_data.gd" type="Script" id=1]
[ext_resource path="res://zones/zone_1/001/group_1.tres" type="Resource" id=4]
[resource]
script = ExtResource( 1 )
wave_duration = 20
max_enemies = 100
groups_data = [ ExtResource( 4 ) ]
conditional_groups_data = [  ]
"""
_GROUP = """[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://zones/wave_group_data.gd" type="Script" id=1]
[ext_resource path="res://zones/zone_1/001/unit_1.tres" type="Resource" id=2]
[resource]
script = ExtResource( 1 )
spawn_chance = 1.0
spawn_timing = 1
repeating = 5
repeating_interval = 3
area = -1
wave_units_data = [ ExtResource( 2 ) ]
is_boss = false
is_horde = false
is_loot = false
min_difficulty = 0
max_difficulty = 9999
"""
_UNIT = """[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://zones/wave_unit_data.gd" type="Script" id=1]
[ext_resource path="res://entities/units/enemies/baby_alien/baby_alien.tscn" type="PackedScene" id=2]
[resource]
script = ExtResource( 1 )
type = 1
unit_scene = ExtResource( 2 )
unit_scene_name = "baby_alien.tscn"
min_number = 5
max_number = 5
spawn_chance = 1.0
"""


def _extracted(root, *, with_enemy=True):
    """A tiny extracted/ tree: one item, one zone_1 wave, optionally its enemy."""
    item = root / "items" / "all" / "handcuffs"
    item.mkdir(parents=True)
    (item / "handcuffs_data.tres").write_text(_ITEM_DATA, encoding="utf-8")
    (item / "handcuffs_effect_1.tres").write_text(_ITEM_EFFECT, encoding="utf-8")
    wave = root / "zones" / "zone_1" / "001"
    wave.mkdir(parents=True)
    (wave / "wave_1.tres").write_text(_WAVE, encoding="utf-8")
    (wave / "group_1.tres").write_text(_GROUP, encoding="utf-8")
    (wave / "unit_1.tres").write_text(_UNIT, encoding="utf-8")
    if with_enemy:
        enemy = root / "entities" / "units" / "enemies" / "baby_alien"
        enemy.mkdir(parents=True)
        (enemy / "baby_alien_stats.tres").write_text("[resource]\nhealth = 3\n", encoding="utf-8")
        (enemy / "baby_alien.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return root


def test_build_dataset_writes_json(tmp_path):
    extracted = _extracted(tmp_path / "extracted")
    out = tmp_path / "data" / "brotato.json"

    ds = build_dataset(extracted, out, "1.1.15.4", generated_at="2026-10-22T00:00:00Z")

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == ds
    assert written["game_version"] == "1.1.15.4"
    assert [i["id"] for i in written["items"]] == ["item_handcuffs"]
    assert [e["id"] for e in written["enemies"]] == ["baby_alien"]
    assert written["enemies"][0]["appears_in"] == ["normal"]
    assert [w["wave"] for w in written["zone_1_waves"]] == [1]
    assert written["zone_1_waves"][0]["groups"][0]["enemy_id"] == "baby_alien"
    assert written["weapons"] == [] and written["characters"] == [] and written["sets"] == []


def test_build_dataset_validation_failure_raises_and_writes_nothing(tmp_path):
    # The wave references baby_alien but no enemy dir exists: validation must fail.
    extracted = _extracted(tmp_path / "extracted", with_enemy=False)
    out_dir = tmp_path / "data"
    out = out_dir / "brotato.json"

    with pytest.raises(ValueError, match="unknown enemy 'baby_alien'"):
        build_dataset(extracted, out, "1.1.15.4", generated_at="2026-10-22T00:00:00Z")
    assert not out_dir.exists()


def test_build_dataset_merges_dlc(tmp_path):
    from dlc_tree import BASE_NAMES, DLC_NAMES, make_tree

    extracted = make_tree(tmp_path / "extracted")
    out = tmp_path / "brotato.json"
    ds = build_dataset(extracted, out, "1.1.15.4", generated_at="2026-10-22T00:00:00Z")

    for coll, prefix, key in (
        ("items", "item_", "item"),
        ("characters", "character_", "character"),
        ("weapons", "weapon_", "weapon"),
        ("sets", "set_", "set"),
        ("enemies", "", "enemy"),
    ):
        recs = ds[coll]
        assert len(recs) == 2, coll  # base + dlc
        ids = [r["id"] for r in recs]
        assert len(set(ids)) == len(ids), coll
        by_id = {r["id"]: r for r in recs}
        assert by_id[prefix + BASE_NAMES[key]]["dlc"] is None
        assert by_id[prefix + DLC_NAMES[key]]["dlc"] == "dlc_1"
        assert by_id[prefix + DLC_NAMES[key]]["source"] == "dlc_1"
        assert by_id[prefix + BASE_NAMES[key]]["source"] == "base"
    assert ds["content_sources"] == ["base", "dlc_1"]


def test_build_dataset_rejects_duplicate_ids_across_sources(tmp_path):
    from dlc_tree import make_tree

    extracted = make_tree(tmp_path / "extracted")
    # A DLC item whose folder repeats a base item id must fail, not shadow it.
    dup = extracted / "dlcs" / "dlc_1" / "items" / "test_anvil"
    src = extracted / "items" / "all" / "test_anvil" / "test_anvil_data.tres"
    dup.mkdir(parents=True)
    (dup / "test_anvil_data.tres").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate item id 'item_test_anvil'"):
        build_dataset(extracted, tmp_path / "o.json", "1.1.15.4", generated_at="x")


def test_build_merges_multiple_translation_csvs(tmp_path):
    from dlc_tree import make_tree

    extracted = make_tree(tmp_path / "extracted")
    base_csv = tmp_path / "translations.csv"
    base_csv.write_text(
        "﻿key,en\nTEST_ANVIL,Anvil (base)\nTEST_SHELL,Shell (base)\n", encoding="utf-8"
    )
    dlc_csv = tmp_path / "translations.dlc_1.csv"
    dlc_csv.write_text("key,en\nTEST_SHELL,Shell (dlc)\n", encoding="utf-8")

    ds = build_dataset(
        extracted,
        tmp_path / "o.json",
        "1.1.15.4",
        translations=[base_csv, dlc_csv],
        generated_at="x",
    )
    names = {i["id"]: i["display_name"] for i in ds["items"]}
    assert names["item_test_anvil"] == "Anvil (base)"
    assert names["item_test_shell"] == "Shell (dlc)"  # the later file wins

    single = build_dataset(
        extracted, tmp_path / "o2.json", "1.1.15.4", translations=base_csv, generated_at="x"
    )
    assert {i["id"]: i["display_name"] for i in single["items"]}["item_test_shell"] == (
        "Shell (base)"
    )
