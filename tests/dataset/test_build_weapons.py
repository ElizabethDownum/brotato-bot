# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
import pytest

from brotato_bot.dataset.spud.builders.weapons import build_weapon_record

STATS = """[gd_resource type="Resource" format=2]
[resource]
cooldown = 45
damage = 25
accuracy = 1.0
crit_chance = 0.03
crit_damage = 2.0
recoil_duration = 0.15
piercing = 3
nb_projectiles = 1
scaling_stats = [ [ "stat_ranged_damage", 0.5 ] ]
can_have_negative_knockback = false
knockback = 0
"""

DATA = """[gd_resource type="Resource" format=2]
[resource]
weapon_id = "weapon_shredder"
tier = 3
effects = [  ]
"""


def test_weapon_record_core_fields():
    rec = build_weapon_record(STATS, DATA, weapon_id="weapon_shredder",
                              name="Shredder", tier=4)
    assert rec["id"] == "weapon_shredder"
    assert rec["tier"] == 4
    assert rec["base_damage"] == 25
    assert rec["scaling_stats"] == [["stat_ranged_damage", 0.5]]
    assert rec["can_have_negative_knockback"] is False


# --- Knife T1 fixture: real melee weapon .tres content (script ext_resource
# identifies the weapon-type stats script), used for the raw-field tests. ---
KNIFE_STATS = """[gd_resource type="Resource" format=2]
[ext_resource path="res://weapons/weapon_stats/melee_weapon_stats.gd" type="Script" id=1]
[resource]
script = ExtResource( 1 )
cooldown = 25
damage = 9
accuracy = 1.0
crit_chance = 0.2
crit_damage = 2.5
max_range = 150
knockback = 2
can_have_negative_knockback = false
scaling_stats = [ [ "stat_melee_damage", 0.8 ] ]
recoil_duration = 0.1
additional_cooldown_every_x_shots = -1
additional_cooldown_multiplier = -1.0
"""

KNIFE_DATA = """[gd_resource type="Resource" format=2]
[resource]
weapon_id = "weapon_knife"
tier = 1
effects = [  ]
"""

PISTOL_STATS = """[gd_resource type="Resource" format=2]
[ext_resource path="res://weapons/weapon_stats/ranged_weapon_stats.gd" type="Script" id=1]
[resource]
script = ExtResource( 1 )
cooldown = 60
damage = 12
accuracy = 0.9
crit_chance = 0.1
crit_damage = 2.0
max_range = 400
knockback = 15
can_have_negative_knockback = false
scaling_stats = [ [ "stat_ranged_damage", 1.0 ] ]
recoil_duration = 0.1
"""


def build_knife_t1():
    return build_weapon_record(KNIFE_STATS, KNIFE_DATA, weapon_id="weapon_knife",
                               name="Knife", tier=1)


def build_pistol_t1():
    return build_weapon_record(PISTOL_STATS, KNIFE_DATA, weapon_id="weapon_pistol",
                               name="Pistol", tier=1)


def build_weapon_with_scaling(scaling_stats):
    scaling_str = "[ " + ", ".join(
        f'[ "{n}", {c} ]' for n, c in scaling_stats) + " ]"
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 45\ndamage = 25\naccuracy = 1.0\nrecoil_duration = 0.15\n'
             f'scaling_stats = {scaling_str}\n')
    data = '[gd_resource type="Resource" format=2]\n[resource]\neffects = [  ]\n'
    return build_weapon_record(stats, data, weapon_id="w", name="W", tier=1)


def test_record_carries_raw_timing_and_type_fields():
    rec = build_knife_t1()
    assert rec["weapon_type"] == "melee"
    assert rec["recoil_duration"] == pytest.approx(0.1)
    assert rec["max_range"] == 150.0
    assert rec["attack_speed_mod"] == 0.0
    assert rec["additional_cooldown_every_x_shots"] == -1
    for dropped in ("cycle_time", "dps_at_zero_rd", "dps_slope_per_rd",
                    "proc_dps_at_zero_rd", "proc_dps_slope_per_rd"):
        assert dropped not in rec


def test_record_detects_ranged_weapon_type():
    rec = build_pistol_t1()
    assert rec["weapon_type"] == "ranged"


def test_record_weapon_type_defaults_ranged_without_script_ext_resource():
    # Fixtures without a script ext_resource (most tests in this file) fall
    # back to "ranged" rather than raising.
    rec = build_weapon_record(STATS, DATA, weapon_id="weapon_shredder",
                              name="Shredder", tier=4)
    assert rec["weapon_type"] == "ranged"


def test_unknown_scaling_stat_fails_build():
    with pytest.raises(ValueError, match="unknown scaling stat"):
        build_weapon_with_scaling([["stat_bananas", 1.0]])


def test_weapon_record_burst_reload_raw_fields():
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 11\ndamage = 40\naccuracy = 0.9\nrecoil_duration = 0.1\n'
             'scaling_stats = [ [ "stat_ranged_damage", 2.0 ] ]\n'
             'additional_cooldown_every_x_shots = 6\nadditional_cooldown_multiplier = 8.0\n')
    data = '[gd_resource type="Resource" format=2]\n[resource]\neffects = [  ]\n'
    rec = build_weapon_record(stats, data, weapon_id="w", name="W", tier=4)
    assert rec["additional_cooldown_every_x_shots"] == 6
    assert rec["additional_cooldown_multiplier"] == 8.0
    assert rec["burst_reload"] is True


def test_weapon_record_populates_effects_and_classes():
    effect = ('[gd_resource type="Resource" format=2]\n'
              '[ext_resource path="res://effects/weapons/exploding_effect.gd" type="Script" id=1]\n'
              '[resource]\nscript = ExtResource( 1 )\n'
              'key = "effect_explode_custom"\nchance = 0.5\nvalue = 0\n')
    rec = build_weapon_record(STATS, DATA, [effect], weapon_id="w", name="W",
                              tier=1, classes=["Gun", "Explosive"])
    assert rec["sets"] == ["Gun", "Explosive"]
    assert len(rec["effects"]) == 1
    e = rec["effects"][0]
    assert e["key"] == "effect_explode_custom"
    assert e["chance"] == 0.5
    assert "__ext__" not in str(e)  # nested resource refs (script) dropped


def test_resolve_weapon_refs_follows_effect_and_set_ext_resources(tmp_path):
    from brotato_bot.dataset.spud.builders import discover
    wdir = tmp_path / "weapons" / "ranged" / "shredder" / "1"
    wdir.mkdir(parents=True)
    (wdir / "shredder_effect.tres").write_text(
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'key = "effect_explode_custom"\nchance = 0.5\n', encoding="utf-8")
    data = wdir / "shredder_data.tres"
    data.write_text(
        '[gd_resource type="Resource" format=2]\n'
        '[ext_resource path="res://weapons/ranged/shredder/1/shredder_effect.tres" type="Resource" id=6]\n'
        '[ext_resource path="res://items/sets/gun/gun_set_data.tres" type="Resource" id=7]\n'
        '[ext_resource path="res://items/sets/explosive/explosive_set_data.tres" type="Resource" id=8]\n'
        '[resource]\neffects = [ ExtResource( 6 ) ]\n'
        'sets = [ ExtResource( 7 ), ExtResource( 8 ) ]\n', encoding="utf-8")
    effect_paths, classes = discover._resolve_weapon_refs(str(tmp_path), str(data))
    assert classes == ["Gun", "Explosive"]
    assert len(effect_paths) == 1
    assert effect_paths[0].endswith("shredder_effect.tres")


EXPLODE_EFFECT = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                  'key = "effect_explode_custom"\nchance = 0.5\nvalue = 0\n')

PROC_MODEL = {"effect_explode_custom": {
    "damage_source": "weapon_damage",
    "damage_multiplier": 1.0,
    "default_enemies_hit": 1.0,
}}


def test_weapon_record_weapon_damage_proc_descriptor():
    rec = build_weapon_record(STATS, DATA, [EXPLODE_EFFECT], weapon_id="w",
                              name="W", tier=4, proc_models=PROC_MODEL)
    assert rec["proc_effects"] == [
        {"kind": "weapon_damage", "chance": 0.5, "enemies_hit": 1.0, "multiplier": 1.0}]
    assert rec["unmodeled_effects"] == []


def test_weapon_record_unmodeled_effect_contributes_no_descriptor_and_is_listed():
    # effect_burning has a PROC_MODELS entry, but this fixture builds it
    # with no burning_data companion resolved, so `bd.get("chance", 0.0)`
    # defaults to 0.0, failing the chance == 1.0 gate and falling back to
    # unmodeled — same outcome as an effect with no model at all.
    burning_effect = EXPLODE_EFFECT.replace("effect_explode_custom", "effect_burning")
    rec = build_weapon_record(STATS, DATA, [burning_effect], weapon_id="w",
                              name="W", tier=4)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_burning"]


def test_default_proc_models_cover_explode_keys():
    for key in ("effect_explode_custom", "effect_explode", "effect_explode_melee"):
        effect = EXPLODE_EFFECT.replace("effect_explode_custom", key)
        rec = build_weapon_record(STATS, DATA, [effect], weapon_id="w",
                                  name="W", tier=4)  # no injected models: real table
        assert rec["proc_effects"] == [
            {"kind": "weapon_damage", "chance": 0.5, "enemies_hit": 1.0, "multiplier": 1.0}], key
        assert rec["unmodeled_effects"] == [], key


def test_weapon_record_no_effects_has_no_proc_effects():
    rec = build_weapon_record(STATS, DATA, weapon_id="w", name="W", tier=4)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == []


DATA_LOC = """[gd_resource type="Resource" format=2]
[resource]
weapon_id = "weapon_shredder"
name = "WEAPON_SHREDDER"
description = "WEAPON_SHREDDER_DESC"
effects = [  ]
"""
TR = {"WEAPON_SHREDDER": "Shredder (EN)",
      "WEAPON_SHREDDER_DESC": "Chance to explode."}


def test_weapon_record_resolves_display_name_and_description():
    rec = build_weapon_record(STATS, DATA_LOC, weapon_id="weapon_shredder",
                              name="Shredder", tier=4, tr=TR)
    assert rec["display_name"] == "Shredder (EN)"
    assert rec["description"] == "Chance to explode."


def test_weapon_record_falls_back_to_slug_name_without_translations():
    rec = build_weapon_record(STATS, DATA_LOC, weapon_id="weapon_shredder",
                              name="Shredder", tier=4)
    assert rec["display_name"] == "Shredder"
    assert rec["description"] == ""


BURNING_EFFECT = ('[gd_resource type="Resource" format=2]\n'
                  '[ext_resource path="res://effects/weapons/burning_effect.gd" type="Script" id=1]\n'
                  '[resource]\nscript = ExtResource( 1 )\n'
                  'key = "effect_burning"\nvalue = 0\n')

BURNING_DATA = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                'chance = 1.0\ndamage = 3\nduration = 3\nspread = 0\n'
                'scaling_stats = [ [ "stat_elemental_damage", 1.0 ] ]\n'
                'is_global_burn = false\n')


def test_weapon_record_merges_burning_data_companion():
    rec = build_weapon_record(STATS, DATA, [BURNING_EFFECT], [{"burning_data": BURNING_DATA}],
                              weapon_id="w", name="W", tier=1)
    e = rec["effects"][0]
    assert e["key"] == "effect_burning"
    assert e["burning_data"] == {
        "chance": 1.0, "damage": 3, "duration": 3, "spread": 0,
        "scaling_stats": [["stat_elemental_damage", 1.0]],
        "is_global_burn": False,
    }


def test_weapon_record_effect_without_companion_has_no_burning_data_key():
    rec = build_weapon_record(STATS, DATA, [BURNING_EFFECT],
                              weapon_id="w", name="W", tier=1)
    assert "burning_data" not in rec["effects"][0]


def _burning_data(chance=1.0, damage=3, duration=3):
    return ('[gd_resource type="Resource" format=2]\n[resource]\n'
            f'chance = {chance}\ndamage = {damage}\nduration = {duration}\n'
            'spread = 0\nscaling_stats = [ [ "stat_elemental_damage", 1.0 ] ]\n'
            'is_global_burn = false\n')


def test_weapon_record_burn_dot_descriptor_when_preconditions_hold():
    # Torch T1: cooldown 31 frames, recoil 0.1 -> cycle_time ~0.717s;
    # duration 3 ticks * 0.5s tick_interval = 1.5s window comfortably
    # sustains continuous uptime.
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 31\ndamage = 5\naccuracy = 1.0\nrecoil_duration = 0.1\n'
             'scaling_stats = [ [ "stat_melee_damage", 1.0 ] ]\n')
    rec = build_weapon_record(stats, DATA, [BURNING_EFFECT], [{"burning_data": _burning_data()}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == [
        {"kind": "burn_dot", "damage": 3.0,
         "scaling_stats": [["stat_elemental_damage", 1.0]], "tick_interval": 0.5}]
    assert rec["unmodeled_effects"] == []


def test_weapon_record_burn_dot_falls_back_when_cycle_time_exceeds_window():
    # Hypothetical slow weapon: cooldown 600 frames (10s) vs. a 1.5s window.
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 600\ndamage = 5\naccuracy = 1.0\nrecoil_duration = 0.1\n'
             'scaling_stats = [ [ "stat_melee_damage", 1.0 ] ]\n')
    rec = build_weapon_record(stats, DATA, [BURNING_EFFECT], [{"burning_data": _burning_data()}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_burning"]


def test_weapon_record_burn_dot_falls_back_when_chance_below_one():
    rec = build_weapon_record(STATS, DATA, [BURNING_EFFECT],
                              [{"burning_data": _burning_data(chance=0.5)}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_burning"]


def test_weapon_record_burn_dot_falls_back_without_burning_data():
    rec = build_weapon_record(STATS, DATA, [BURNING_EFFECT],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_burning"]


def test_weapon_record_burn_dot_falls_back_when_damage_missing():
    # chance == 1.0 and duration comfortably clear the window gate (same
    # cycle_time setup as test_weapon_record_burn_dot_descriptor_when_
    # preconditions_hold), but the burning_data companion has no `damage`
    # key at all. This must NOT be modeled as a descriptor -- it must fall
    # back to unmodeled_effects, same as any other missing field.
    burning_data_no_damage = (
        '[gd_resource type="Resource" format=2]\n[resource]\n'
        'chance = 1.0\nduration = 3\nspread = 0\n'
        'scaling_stats = [ [ "stat_elemental_damage", 1.0 ] ]\n'
        'is_global_burn = false\n')
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 31\ndamage = 5\naccuracy = 1.0\nrecoil_duration = 0.1\n'
             'scaling_stats = [ [ "stat_melee_damage", 1.0 ] ]\n')
    rec = build_weapon_record(stats, DATA, [BURNING_EFFECT], [{"burning_data": burning_data_no_damage}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_burning"]


def test_weapon_effect_record_carries_script_basename():
    effect = ('[gd_resource type="Resource" format=2]\n'
              '[ext_resource path="res://effects/weapons/one_shot_on_hit_effect.gd" type="Script" id=1]\n'
              '[resource]\nscript = ExtResource( 1 )\nkey = ""\nvalue = 1\n')
    rec = build_weapon_record(STATS, DATA, [effect], weapon_id="w", name="W", tier=2)
    assert rec["effects"][0]["script"] == "one_shot_on_hit_effect.gd"


def test_weapon_effect_record_nests_weapon_stats_companion():
    effect = ('[gd_resource type="Resource" format=2]\n'
              '[ext_resource path="res://effects/weapons/projectiles_on_hit_effect.gd" type="Script" id=1]\n'
              '[resource]\nscript = ExtResource( 1 )\nkey = "effect_lightning_on_hit"\n'
              'value = 1\nauto_target_enemy = true\n')
    companion = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                 'damage = 5\nbounce = 0\nbounce_dmg_reduction = 0.0\ncan_bounce = true\n'
                 'scaling_stats = [ [ "stat_elemental_damage", 0.8 ] ]\n')
    rec = build_weapon_record(STATS, DATA, [effect], [{"weapon_stats": companion}],
                              weapon_id="w", name="W", tier=1)
    ws = rec["effects"][0]["weapon_stats"]
    assert ws["damage"] == 5
    assert ws["bounce"] == 0


def _projectile_effect(key="effect_lightning_on_hit", value=1, auto_target="true"):
    return ('[gd_resource type="Resource" format=2]\n'
            '[ext_resource path="res://effects/weapons/projectiles_on_hit_effect.gd" type="Script" id=1]\n'
            '[resource]\nscript = ExtResource( 1 )\n'
            f'key = "{key}"\nvalue = {value}\nauto_target_enemy = {auto_target}\n')


def _companion_stats(damage=5, scaling='[ [ "stat_elemental_damage", 0.8 ] ]',
                     bounce=0, bounce_dmg_reduction=0.0, can_bounce="true"):
    return ('[gd_resource type="Resource" format=2]\n[resource]\n'
            f'damage = {damage}\nscaling_stats = {scaling}\n'
            f'bounce = {bounce}\nbounce_dmg_reduction = {bounce_dmg_reduction}\n'
            f'can_bounce = {can_bounce}\n')


# Host: cooldown 27, recoil 0.1 -> cycle_time 0.65s (lightning_shiv T1)
LIGHTNING_HOST = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                  'cooldown = 27\ndamage = 5\naccuracy = 1.0\nrecoil_duration = 0.1\n'
                  'scaling_stats = [ [ "stat_melee_damage", 1.0 ] ]\n')


def test_weapon_record_targeted_companion_descriptor_counts_chain():
    # bounce 3 (lightning_shiv T4-style chain) -> enemies_hit 1+3
    rec = build_weapon_record(LIGHTNING_HOST, DATA, [_projectile_effect()],
                              [{"weapon_stats": _companion_stats(bounce=3)}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == [
        {"kind": "companion", "damage": 5.0,
         "scaling_stats": [["stat_elemental_damage", 0.8]],
         "crit_chance": 0.0, "crit_damage": 0.0, "count": 1.0, "enemies_hit": 4.0}]
    assert rec["unmodeled_effects"] == []


def test_weapon_record_targeted_falls_back_on_lossy_bounce():
    rec = build_weapon_record(
        LIGHTNING_HOST, DATA, [_projectile_effect()],
        [{"weapon_stats": _companion_stats(bounce=2, bounce_dmg_reduction=0.5)}],
        weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_lightning_on_hit"]


def test_weapon_record_spray_companion_descriptor_carries_scaling_stats():
    # cactus_mace T1: 3 spawns, damage 1, stat_ranged_damage 0.6
    host = ('[gd_resource type="Resource" format=2]\n[resource]\n'
            'cooldown = 63\ndamage = 15\naccuracy = 1.0\nrecoil_duration = 0.1\n'
            'scaling_stats = [ [ "stat_melee_damage", 0.8 ] ]\n')
    rec = build_weapon_record(
        host, DATA,
        [_projectile_effect(key="effect_projectiles_on_hit", value=3, auto_target="false")],
        [{"weapon_stats": _companion_stats(
            damage=1, scaling='[ [ "stat_ranged_damage", 0.6 ] ]',
            bounce=0, bounce_dmg_reduction=0.5)}],
        weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == [
        {"kind": "companion", "damage": 1.0,
         "scaling_stats": [["stat_ranged_damage", 0.6]],
         "crit_chance": 0.0, "crit_damage": 0.0, "count": 3.0, "enemies_hit": 1.0}]
    assert rec["unmodeled_effects"] == []


def test_weapon_record_spray_falls_back_when_bouncing():
    rec = build_weapon_record(
        LIGHTNING_HOST, DATA,
        [_projectile_effect(key="EFFECT_PROJECTILES_ON_HIT", value=8, auto_target="false")],
        [{"weapon_stats": _companion_stats(bounce=1, bounce_dmg_reduction=0.5)}],
        weapon_id="w", name="W", tier=3)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["EFFECT_PROJECTILES_ON_HIT"]


def test_weapon_record_companion_proc_falls_back_without_companion():
    rec = build_weapon_record(LIGHTNING_HOST, DATA, [_projectile_effect()],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"] == []
    assert rec["unmodeled_effects"] == ["effect_lightning_on_hit"]


def test_weapon_record_targeted_companion_defaults_can_bounce_true():
    # companion omits can_bounce entirely -> engine default True keeps bounce
    companion = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                 'damage = 5\nscaling_stats = [ [ "stat_elemental_damage", 0.8 ] ]\n'
                 'bounce = 3\nbounce_dmg_reduction = 0.0\n')
    rec = build_weapon_record(LIGHTNING_HOST, DATA, [_projectile_effect()],
                              [{"weapon_stats": companion}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"][0]["enemies_hit"] == 4.0


def test_weapon_record_targeted_can_bounce_false_forces_single_hit():
    # can_bounce=false zeroes the chain even with bounce=3 and lossy reduction
    companion = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                 'damage = 5\nscaling_stats = [ [ "stat_elemental_damage", 0.8 ] ]\n'
                 'bounce = 3\nbounce_dmg_reduction = 0.5\ncan_bounce = false\n')
    rec = build_weapon_record(LIGHTNING_HOST, DATA, [_projectile_effect()],
                              [{"weapon_stats": companion}],
                              weapon_id="w", name="W", tier=1)
    # forced bounce=0 passes the gate
    assert rec["proc_effects"] == [
        {"kind": "companion", "damage": 5.0,
         "scaling_stats": [["stat_elemental_damage", 0.8]],
         "crit_chance": 0.0, "crit_damage": 0.0, "count": 1.0, "enemies_hit": 1.0}]
    assert rec["unmodeled_effects"] == []


def test_weapon_record_companion_omitting_bounce_fields_uses_engine_defaults():
    # bounce/bounce_dmg_reduction/can_bounce all absent -> bounce defaults 0;
    # the 0.5 reduction default is irrelevant at bounce 0; models one hit
    companion = ('[gd_resource type="Resource" format=2]\n[resource]\n'
                 'damage = 5\nscaling_stats = [ [ "stat_elemental_damage", 0.8 ] ]\n')
    rec = build_weapon_record(LIGHTNING_HOST, DATA, [_projectile_effect()],
                              [{"weapon_stats": companion}],
                              weapon_id="w", name="W", tier=1)
    assert rec["proc_effects"][0]["enemies_hit"] == 1.0
    assert rec["unmodeled_effects"] == []


def test_weapon_record_classifies_stat_rider_out_of_unmodeled():
    effect = ('[gd_resource type="Resource" format=2]\n'
              '[ext_resource path="res://items/global/effect.gd" type="Script" id=1]\n'
              '[resource]\nscript = ExtResource( 1 )\nkey = "stat_armor"\nvalue = 1\n')
    rec = build_weapon_record(STATS, DATA, [effect], weapon_id="w", name="W", tier=2)
    assert rec["unmodeled_effects"] == []
    assert rec["classified_effects"] == [
        {"key": "stat_armor", "category": "stat_rider", "value": 1}]


def test_weapon_record_blank_key_unknown_script_surfaces_in_unmodeled():
    effect = ('[gd_resource type="Resource" format=2]\n'
              '[ext_resource path="res://effects/weapons/mystery_effect.gd" type="Script" id=1]\n'
              '[resource]\nscript = ExtResource( 1 )\nkey = ""\nvalue = 1\n')
    rec = build_weapon_record(STATS, DATA, [effect], weapon_id="w", name="W", tier=1)
    assert rec["classified_effects"] == []
    assert rec["unmodeled_effects"] == ["mystery_effect.gd"]


def test_weapon_record_burn_gate_failure_stays_unmodeled_not_classified():
    rec = build_weapon_record(STATS, DATA, [BURNING_EFFECT],
                              [{"burning_data": _burning_data(chance=0.5)}],
                              weapon_id="w", name="W", tier=1)
    assert rec["unmodeled_effects"] == ["effect_burning"]
    assert rec["classified_effects"] == []


def test_weapon_record_marks_burst_reload_false_for_normal_weapon():
    rec = build_weapon_record(STATS, DATA, weapon_id="weapon_shredder",
                              name="Shredder", tier=4)
    assert rec["burst_reload"] is False


def test_weapon_record_marks_burst_reload_true_for_revolver():
    stats = ('[gd_resource type="Resource" format=2]\n[resource]\n'
             'cooldown = 11\ndamage = 40\naccuracy = 0.9\nrecoil_duration = 0.1\n'
             'scaling_stats = [ [ "stat_ranged_damage", 2.0 ] ]\n'
             'additional_cooldown_every_x_shots = 6\nadditional_cooldown_multiplier = 8.0\n')
    data = '[gd_resource type="Resource" format=2]\n[resource]\neffects = [  ]\n'
    rec = build_weapon_record(stats, data, weapon_id="w", name="W", tier=4)
    assert rec["burst_reload"] is True
