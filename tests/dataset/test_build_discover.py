# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.discover import (
    find_weapon_dirs, find_item_dirs, find_character_dirs, find_set_dirs,
    find_challenge_paths)


def test_find_challenge_paths_excludes_global_schema_dir(tmp_path):
    d = tmp_path / "challenges"
    d.mkdir(parents=True)
    (d / "agriculture_data.tres").write_text("data")
    (d / "apprentice_data.tres").write_text("data")
    global_dir = d / "global"
    global_dir.mkdir()
    (global_dir / "challenge_data.gd").write_text("class_name ChallengeData")

    found = find_challenge_paths(str(tmp_path))
    assert [p.replace("\\", "/").split("/")[-1] for p in found] == [
        "agriculture_data.tres", "apprentice_data.tres"]


def test_find_weapon_dirs(tmp_path):
    d = tmp_path / "weapons" / "ranged" / "shredder" / "4"
    d.mkdir(parents=True)
    (d / "shredder_4_stats.tres").write_text("stats")
    (d / "shredder_4_data.tres").write_text("data")

    found = find_weapon_dirs(str(tmp_path))
    assert len(found) == 1
    entry = found[0]
    assert entry["weapon_id"] == "weapon_shredder"
    assert entry["tier"] == 4
    assert entry["stats_path"].endswith("shredder_4_stats.tres")
    assert entry["data_path"].endswith("shredder_4_data.tres")


def test_find_item_dirs(tmp_path):
    d = tmp_path / "items" / "all" / "handcuffs"
    d.mkdir(parents=True)
    (d / "handcuffs_data.tres").write_text("data")
    (d / "handcuffs_effect_1.tres").write_text("e1")
    (d / "handcuffs_effect_2.tres").write_text("e2")
    # a dir with no item_data.gd resource at all is skipped
    empty = tmp_path / "items" / "all" / "not_an_item"
    empty.mkdir(parents=True)
    (empty / "not_an_item.png.import").write_text("x")
    # a dir whose only .tres references a different script is also skipped —
    # exercises the fallback loop rejecting a non-item_data.gd resource. Named
    # "unrelated.tres" (not "unrelated_data.tres") so it misses the standard-
    # name fast path and actually reaches the script check.
    unrelated = tmp_path / "items" / "all" / "unrelated"
    unrelated.mkdir(parents=True)
    (unrelated / "unrelated.tres").write_text(
        '[gd_resource type="Resource" load_steps=2 format=2]\n\n'
        '[ext_resource path="res://items/global/some_other.gd" type="Script" id=1]\n\n'
        '[resource]\n'
        'script = ExtResource( 1 )\n'
    )
    found = find_item_dirs(str(tmp_path))
    assert len(found) == 1
    e = found[0]
    assert e["item_id"] == "item_handcuffs"
    assert e["name"] == "Handcuffs"
    assert len(e["effect_paths"]) == 2


def test_find_item_dirs_pet_style_bare_data_file(tmp_path):
    # Pets (and a few other items, e.g. evil_hat) ship their main data file
    # as a bare "{folder}.tres" instead of the usual "{folder}_data.tres".
    d = tmp_path / "items" / "all" / "lootworm"
    d.mkdir(parents=True)
    (d / "lootworm.tres").write_text(
        '[gd_resource type="Resource" load_steps=2 format=2]\n\n'
        '[ext_resource path="res://items/global/item_data.gd" type="Script" id=1]\n\n'
        '[resource]\n'
        'script = ExtResource( 1 )\n'
        'my_id = "item_lootworm"\n'
        'tags = [ "economy", "pickup", "pet" ]\n'
    )
    (d / "lootworm_effect_0.tres").write_text("e0")

    found = find_item_dirs(str(tmp_path))
    assert len(found) == 1
    e = found[0]
    assert e["item_id"] == "item_lootworm"
    assert e["name"] == "Lootworm"
    assert e["data_path"].endswith("lootworm.tres")
    assert len(e["effect_paths"]) == 1


def test_find_item_dirs_folder_name_mismatched_with_file_prefix(tmp_path):
    # eyes_surgery: the folder is plural but its files use the singular
    # "eye_surgery" prefix, so effect discovery can't assume folder == prefix.
    d = tmp_path / "items" / "all" / "eyes_surgery"
    d.mkdir(parents=True)
    (d / "eye_surgery_data.tres").write_text(
        '[gd_resource type="Resource" load_steps=2 format=2]\n\n'
        '[ext_resource path="res://items/global/item_data.gd" type="Script" id=1]\n\n'
        '[resource]\n'
        'script = ExtResource( 1 )\n'
        'my_id = "item_eyes_surgery"\n'
    )
    (d / "eye_surgery_effect_1.tres").write_text("e1")
    (d / "eye_surgery_effect_2.tres").write_text("e2")

    found = find_item_dirs(str(tmp_path))
    assert len(found) == 1
    e = found[0]
    assert e["item_id"] == "item_eyes_surgery"
    assert e["data_path"].endswith("eye_surgery_data.tres")
    assert len(e["effect_paths"]) == 2


def test_find_character_dirs(tmp_path):
    d = tmp_path / "items" / "characters" / "ranger"
    d.mkdir(parents=True)
    (d / "ranger_data.tres").write_text("data")
    (d / "ranger_effect_2.tres").write_text("e2")  # note: starts at _2
    found = find_character_dirs(str(tmp_path))
    assert len(found) == 1
    assert found[0]["char_id"] == "character_ranger"
    assert len(found[0]["effect_paths"]) == 1


def test_find_set_dirs(tmp_path):
    base = tmp_path / "items" / "sets" / "gun"
    (base / "2").mkdir(parents=True)
    (base / "6").mkdir(parents=True)
    (base / "gun_set_data.tres").write_text("setdata")
    (base / "2" / "set_2_effect_1.tres").write_text("e2")
    (base / "6" / "set_6_effect_1.tres").write_text("e6")
    found = find_set_dirs(str(tmp_path))
    assert len(found) == 1
    e = found[0]
    assert e["set_id"] == "set_gun"
    assert sorted(e["count_effect_paths"].keys()) == [2, 6]


def test_resolve_effect_companions_finds_burning_data(tmp_path):
    from brotato_bot.dataset.spud.builders import discover
    wdir = tmp_path / "weapons" / "melee" / "torch" / "1"
    wdir.mkdir(parents=True)
    effect_path = wdir / "torch_effect_1.tres"
    effect_path.write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://effects/weapons/burning_effect.gd" type="Script" id=1]\n'
        '[ext_resource path="res://weapons/melee/torch/1/torch_burning_data.tres" type="Resource" id=2]\n'
        '[resource]\nscript = ExtResource( 1 )\nkey = "effect_burning"\n'
        'burning_data = ExtResource( 2 )\n', encoding="utf-8")
    (wdir / "torch_burning_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'chance = 1.0\ndamage = 3\nduration = 3\n', encoding="utf-8")

    result = discover._resolve_effect_companions(str(tmp_path), [str(effect_path)])
    assert list(result.keys()) == [str(effect_path)]
    assert result[str(effect_path)]["burning_data"].endswith("torch_burning_data.tres")


def test_resolve_effect_companions_finds_weapon_stats(tmp_path):
    from brotato_bot.dataset.spud.builders import discover
    wdir = tmp_path / "weapons" / "melee" / "lightning_shiv" / "1"
    wdir.mkdir(parents=True)
    effect_path = wdir / "lightning_shiv_effect_1.tres"
    effect_path.write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://effects/weapons/projectiles_on_hit_effect.gd" type="Script" id=1]\n'
        '[ext_resource path="res://weapons/melee/lightning_shiv/1/lightning_shiv_projectile.tres" type="Resource" id=2]\n'
        '[resource]\nscript = ExtResource( 1 )\nkey = "effect_lightning_on_hit"\n'
        'value = 1\nweapon_stats = ExtResource( 2 )\nauto_target_enemy = true\n',
        encoding="utf-8")
    (wdir / "lightning_shiv_projectile.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\ndamage = 5\n',
        encoding="utf-8")

    result = discover._resolve_effect_companions(str(tmp_path), [str(effect_path)])
    assert result[str(effect_path)]["weapon_stats"].endswith("lightning_shiv_projectile.tres")


def test_resolve_effect_companions_finds_structure_stats_outside_weapon_dir(tmp_path):
    from brotato_bot.dataset.spud.builders import discover
    wdir = tmp_path / "weapons" / "melee" / "screwdriver" / "1"
    wdir.mkdir(parents=True)
    mines = tmp_path / "items" / "all" / "landmines"
    mines.mkdir(parents=True)
    (mines / "landmine_stats.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\ndamage = 10\n',
        encoding="utf-8")
    effect_path = wdir / "screwdriver_effect.tres"
    effect_path.write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://effects/items/structure_effect.gd" type="Script" id=1]\n'
        '[ext_resource path="res://items/all/landmines/landmine_stats.tres" type="Resource" id=3]\n'
        '[resource]\nscript = ExtResource( 1 )\nkey = ""\nvalue = 1\n'
        'spawn_cooldown = 12\nstats = ExtResource( 3 )\n', encoding="utf-8")

    result = discover._resolve_effect_companions(str(tmp_path), [str(effect_path)])
    assert result[str(effect_path)]["stats"].endswith("landmine_stats.tres")


def test_resolve_effect_companions_skips_effects_without_any(tmp_path):
    from brotato_bot.dataset.spud.builders import discover
    wdir = tmp_path / "weapons" / "ranged" / "shredder" / "1"
    wdir.mkdir(parents=True)
    effect_path = wdir / "shredder_effect.tres"
    effect_path.write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'key = "effect_explode_custom"\nchance = 0.5\n', encoding="utf-8")

    result = discover._resolve_effect_companions(str(tmp_path), [str(effect_path)])
    assert result == {}


def test_find_weapon_dirs_includes_companion_paths(tmp_path):
    from brotato_bot.dataset.spud.builders.discover import find_weapon_dirs
    wdir = tmp_path / "weapons" / "melee" / "torch" / "1"
    wdir.mkdir(parents=True)
    (wdir / "torch_stats.tres").write_text("stats")
    effect_path = wdir / "torch_effect_1.tres"
    effect_path.write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://effects/weapons/burning_effect.gd" type="Script" id=1]\n'
        '[ext_resource path="res://weapons/melee/torch/1/torch_burning_data.tres" type="Resource" id=2]\n'
        '[resource]\nscript = ExtResource( 1 )\nkey = "effect_burning"\n'
        'burning_data = ExtResource( 2 )\n', encoding="utf-8")
    (wdir / "torch_burning_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'chance = 1.0\ndamage = 3\nduration = 3\n', encoding="utf-8")
    (wdir / "torch_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://weapons/melee/torch/1/torch_effect_1.tres" type="Resource" id=1]\n'
        '[resource]\neffects = [ ExtResource( 1 ) ]\n', encoding="utf-8")

    found = find_weapon_dirs(str(tmp_path))
    assert len(found) == 1
    companions = found[0]["effect_companion_paths"]
    assert len(companions) == 1
    only = next(iter(companions.values()))
    assert only["burning_data"].endswith("torch_burning_data.tres")


def test_find_weapon_dirs_main_data_glob_skips_burning_data_companion(tmp_path):
    # Regression: a burn weapon's tier dir holds both "{w}_data.tres" and its
    # "{w}_burning_data.tres" companion. The latter also matches "*_data.tres"
    # and sorts first alphabetically, so a naive glob[0] picked the wrong file
    # (its effects/display_name were silently empty). The main-data glob must
    # exclude "*_burning_data.tres".
    wdir = tmp_path / "weapons" / "melee" / "torch" / "1"
    wdir.mkdir(parents=True)
    (wdir / "torch_stats.tres").write_text("stats")
    (wdir / "torch_burning_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'chance = 1.0\ndamage = 3\nduration = 3\n', encoding="utf-8")
    (wdir / "torch_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'effects = [ ]\n', encoding="utf-8")

    found = find_weapon_dirs(str(tmp_path))
    assert len(found) == 1
    assert found[0]["data_path"].endswith("torch_data.tres")
    assert not found[0]["data_path"].endswith("torch_burning_data.tres")


def test_find_weapon_dirs_stats_glob_skips_proj_stats_companion(tmp_path):
    # Regression: Sniper Gun's tier dirs hold both "{w}_stats.tres" (the
    # weapon's own stats) and its "{w}_proj_stats.tres" companion (the
    # projectile's stats). The latter also matches "*_stats.tres", and on
    # some filesystems unsorted glob order picked it first, corrupting the
    # shipped weapon_sniper_gun record (wrong base_damage, cooldown,
    # max_range, scaling_stats, recoil_duration). The stats selection must
    # pick the file matching the weapon's exact expected filename rather
    # than any-match-of-"*_stats.tres" -- see the sibling
    # test_find_weapon_dirs_stats_glob_skips_garden_stats_companion below
    # for a second, independently confirmed instance of this bug class
    # (Pruner) that a narrower "*_proj_stats.tres"-only exclusion would miss.
    wdir = tmp_path / "weapons" / "ranged" / "sniper_gun" / "3"
    wdir.mkdir(parents=True)
    (wdir / "sniper_gun_3_proj_stats.tres").write_text("proj stats")
    (wdir / "sniper_gun_3_stats.tres").write_text("real stats")
    (wdir / "sniper_gun_3_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'effects = [ ]\n', encoding="utf-8")

    found = find_weapon_dirs(str(tmp_path))
    assert len(found) == 1
    assert found[0]["stats_path"].endswith("sniper_gun_3_stats.tres")
    assert not found[0]["stats_path"].endswith("proj_stats.tres")


def test_find_weapon_dirs_stats_glob_skips_garden_stats_companion(tmp_path):
    # Regression: a second, independently confirmed instance of the same bug
    # class as the Sniper Gun case above. Pruner's tier 2-4 dirs hold both
    # "pruner_{tier}_stats.tres" (the real melee weapon's own stats,
    # script=melee_weapon_stats.gd) and a "pruner_{tier}_garden_stats.tres"
    # companion (a "garden zapper" ranged turret companion,
    # script=ranged_weapon_stats.gd, damage=0). The latter also matches
    # "*_stats.tres" and was shipping in place of the real weapon's data.
    # A blocklist that only excludes "_proj_stats.tres" misses this one --
    # the fix must be a whitelist (exact filename match), not a blocklist,
    # so it generalizes to companion suffixes we haven't enumerated.
    wdir = tmp_path / "weapons" / "melee" / "pruner" / "2"
    wdir.mkdir(parents=True)
    (wdir / "pruner_2_garden_stats.tres").write_text("garden turret companion stats")
    (wdir / "pruner_2_stats.tres").write_text("real melee weapon stats")
    (wdir / "pruner_2_data.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'effects = [ ]\n', encoding="utf-8")

    found = find_weapon_dirs(str(tmp_path))
    assert len(found) == 1
    assert found[0]["stats_path"].endswith("pruner_2_stats.tres")
    assert not found[0]["stats_path"].endswith("garden_stats.tres")


def test_find_enemy_dirs(tmp_path):
    import os

    from brotato_bot.dataset.spud.builders import discover

    root = tmp_path
    d = root / "entities" / "units" / "enemies" / "baby_alien"
    d.mkdir(parents=True)
    (d / "baby_alien_stats.tres").write_text("[resource]\nhealth = 3\n", encoding="utf-8")
    (d / "baby_alien.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    # a non-enemy sibling dir with no *_stats.tres must be skipped
    (root / "entities" / "units" / "enemies" / "attack_behaviors").mkdir()

    found = discover.find_enemy_dirs(str(root))
    assert len(found) == 1
    e = found[0]
    assert e["enemy_id"] == "baby_alien"
    assert e["name"] == "Baby Alien"
    assert os.path.basename(e["stats_path"]) == "baby_alien_stats.tres"
    assert os.path.basename(e["scene_path"]) == "baby_alien.tscn"


def test_find_enemy_dirs_accepts_bare_stats_tres(tmp_path):
    from brotato_bot.dataset.spud.builders import discover

    d = tmp_path / "entities" / "units" / "enemies" / "evil_mob"
    d.mkdir(parents=True)
    (d / "evil_mob.tres").write_text(
        '[gd_resource]\n'
        '[ext_resource path="res://entities/units/unit/stats.gd" type="Script" id=1]\n'
        '[resource]\nscript = ExtResource( 1 )\nhealth = 10\n', encoding="utf-8")
    (d / "evil_mob.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    found = discover.find_enemy_dirs(str(tmp_path))
    assert [e["enemy_id"] for e in found] == ["evil_mob"]
    assert found[0]["stats_path"].endswith("evil_mob.tres")


def test_coverage_report_empty_on_baseline_dirs(tmp_path):
    from brotato_bot.dataset.spud.builders.discover import coverage_report
    # Only accounted-for baseline dirs present.
    for name in ("weapons", "items", "entities", "zones", "challenges", "ui", "effects"):
        (tmp_path / name).mkdir()
    (tmp_path / "weapons" / "melee").mkdir()
    (tmp_path / "weapons" / "ranged").mkdir()
    (tmp_path / "weapons" / "weapon_stats").mkdir()
    (tmp_path / "zones" / "zone_1").mkdir()
    (tmp_path / "zones" / "zone_2").mkdir()
    (tmp_path / "zones" / "common").mkdir()
    report = coverage_report(str(tmp_path))
    assert report == {"unclaimed_trees": [], "unknown_weapon_kinds": [], "unmodeled_zones": []}


def test_coverage_report_flags_new_content(tmp_path):
    from brotato_bot.dataset.spud.builders.discover import coverage_report
    (tmp_path / "abyssal").mkdir()                       # new top-level tree
    (tmp_path / "weapons").mkdir()
    (tmp_path / "weapons" / "thrown").mkdir()            # new weapon kind
    (tmp_path / "zones").mkdir()
    (tmp_path / "zones" / "zone_4").mkdir()              # new zone
    report = coverage_report(str(tmp_path))
    assert report["unclaimed_trees"] == ["abyssal"]
    assert report["unknown_weapon_kinds"] == ["thrown"]
    assert report["unmodeled_zones"] == ["zone_4"]


def test_coverage_report_ignores_dot_dirs(tmp_path):
    from brotato_bot.dataset.spud.builders.discover import coverage_report
    # Only accounted-for baseline dirs present, plus Godot/tooling cache dirs
    # (dot-prefixed) at every level coverage_report scans. These are never
    # Brotato content and must not surface as unclaimed/unknown/unmodeled.
    for name in ("weapons", "items", "entities", "zones", "challenges", "ui", "effects"):
        (tmp_path / name).mkdir()
    (tmp_path / ".import").mkdir()
    (tmp_path / "weapons" / "melee").mkdir()
    (tmp_path / "weapons" / "ranged").mkdir()
    (tmp_path / "weapons" / "weapon_stats").mkdir()
    (tmp_path / "weapons" / ".import").mkdir()
    (tmp_path / "zones" / "zone_1").mkdir()
    (tmp_path / "zones" / "zone_2").mkdir()
    (tmp_path / "zones" / "common").mkdir()
    (tmp_path / "zones" / ".godot").mkdir()
    report = coverage_report(str(tmp_path))
    assert report == {"unclaimed_trees": [], "unknown_weapon_kinds": [], "unmodeled_zones": []}


def test_find_zone_waves_excludes_test_wave(tmp_path):
    from brotato_bot.dataset.spud.builders import discover

    z = tmp_path / "zones" / "zone_1"
    (z / "001").mkdir(parents=True)
    (z / "001" / "wave_1.tres").write_text(
        '[resource]\ngroups_data = [  ]\n', encoding="utf-8")
    test_dir = z / "021 (test)"
    test_dir.mkdir()
    (test_dir / "wave_21.tres").write_text(
        '[resource]\ngroups_data = [  ]\n', encoding="utf-8")

    waves = discover.find_zone_waves(str(tmp_path))
    assert [w["wave"] for w in waves] == [1]  # wave 21 (test) excluded


def test_find_set_dirs_keeps_every_effect_file_sorted(tmp_path):
    # blunt at 6 weapons: +3 armor, +6 max hp, -10 speed in three files.
    base = tmp_path / "items" / "sets" / "blunt"
    (base / "6").mkdir(parents=True)
    (base / "blunt_set_data.tres").write_text("setdata")
    for n in (3, 1, 2):
        (base / "6" / f"set_6_effect_{n}.tres").write_text(f"e{n}")
    found = find_set_dirs(str(tmp_path))
    paths = found[0]["count_effect_paths"][6]
    assert [p.rsplit("set_6_", 1)[1] for p in paths] == [
        "effect_1.tres",
        "effect_2.tres",
        "effect_3.tres",
    ]
