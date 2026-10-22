# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.classifications import CATEGORIES, classify_effect


def test_flat_sum_stat_key_is_stat_rider():
    entry = classify_effect({"key": "stat_armor", "value": 1, "script": "effect.gd"})
    assert entry == {"key": "stat_armor", "category": "stat_rider", "value": 1}


def test_key_value_storage_is_dynamic_not_rider():
    # jousting_lance's stand-still damage penalty: same key string as a flat
    # rider, but KEY_VALUE storage routes it through a conditional bucket.
    entry = classify_effect({"key": "stat_percent_damage", "value": -10,
                             "storage_method": 1,
                             "custom_key": "temp_stats_while_not_moving",
                             "script": "effect.gd"})
    assert entry == {"key": "stat_percent_damage", "category": "dynamic"}


def test_dynamic_scripts_classify_by_script():
    for script in ("gain_stat_for_every_stat_effect.gd",
                   "temp_stats_per_interval_effect.gd",
                   "gain_stat_every_killed_enemies_effect.gd",
                   "player_no_hit_effect.gd"):
        entry = classify_effect({"key": "stat_lifesteal", "value": 1, "script": script})
        assert entry["category"] == "dynamic", script


def test_cc_scripts():
    assert classify_effect({"key": "EFFECT_WEAPON_SLOW_ON_HIT", "value": 1,
                            "script": "weapon_slow_on_hit_effect.gd"})["category"] == "cc"
    assert classify_effect({"key": "effect_slow_in_zone", "value": 1,
                            "script": "slow_in_zone_effect.gd"})["category"] == "cc"


def test_crit_riders_and_economy():
    pierce = classify_effect({"key": "pierce_on_crit", "value": 4, "script": "null_effect.gd"})
    assert pierce == {"key": "pierce_on_crit", "category": "delivery_modifier",
                      "on_crit_extra_hits_max": 4}
    gold = classify_effect({"key": "gold_on_crit_kill", "value": 50, "script": "null_effect.gd"})
    assert gold == {"key": "gold_on_crit_kill", "category": "economy",
                    "gold_chance_on_crit_kill": 0.5}


def test_drawback():
    entry = classify_effect({"key": "lose_hp_per_second", "value": 3, "script": "effect.gd"})
    assert entry == {"key": "lose_hp_per_second", "category": "drawback",
                     "self_damage_per_second": 3}


def test_execute_names_blank_key_by_mechanic():
    entry = classify_effect({"key": "", "value": 2,
                             "script": "one_shot_on_hit_effect.gd"})
    assert entry == {"key": "one_shot_on_hit", "category": "execute",
                     "execute_chance_per_hit": 0.02}


def test_stack_metadata():
    entry = classify_effect({"key": "EFFECT_WEAPON_STACK", "value": 4,
                             "stat_name": "damage", "weapon_stacked_id": "weapon_stick",
                             "script": "weapon_stack_effect.gd"})
    assert entry == {"key": "EFFECT_WEAPON_STACK", "category": "stack",
                     "stat_name": "damage", "bonus_per_extra_copy": 4}


def test_structure_metadata_reads_stats_companion():
    entry = classify_effect({"key": "", "value": 1, "spawn_cooldown": 12,
                             "script": "structure_effect.gd",
                             "stats": {"damage": 10,
                                       "scaling_stats": [["stat_engineering", 1.0]]}})
    assert entry == {"key": "structure", "category": "structure",
                     "spawn_cooldown": 12, "structure_damage": 10,
                     "structure_scaling_stats": [["stat_engineering", 1.0]]}


def test_structure_turret_sentinel_falls_back_to_stats_cooldown():
    # Spawning turrets (Pruner garden) ship spawn_cooldown = -1; the real
    # cadence is the companion stats' cooldown (frames).
    entry = classify_effect({"key": "", "value": 1, "spawn_cooldown": -1,
                             "script": "turret_effect.gd",
                             "stats": {"cooldown": 840, "damage": 0,
                                       "scaling_stats": []}})
    assert entry["spawn_cooldown"] == 840
    assert entry["structure_damage"] == 0


def test_unknown_effect_is_not_classified():
    assert classify_effect({"key": "effect_burning", "script": "burning_effect.gd"}) is None
    assert classify_effect({"key": "", "script": "mystery_effect.gd"}) is None


def test_all_categories_in_vocabulary():
    samples = [
        {"key": "stat_armor", "value": 1, "script": "effect.gd"},
        {"key": "x", "storage_method": 1, "script": "effect.gd"},
        {"key": "gold_on_crit_kill", "value": 50, "script": "null_effect.gd"},
        {"key": "effect_slow_in_zone", "script": "slow_in_zone_effect.gd"},
        {"key": "pierce_on_crit", "value": 1, "script": "null_effect.gd"},
        {"key": "lose_hp_per_second", "value": 3, "script": "effect.gd"},
        {"key": "", "value": 1, "script": "one_shot_on_hit_effect.gd"},
        {"key": "EFFECT_WEAPON_STACK", "value": 4, "stat_name": "damage",
         "script": "weapon_stack_effect.gd"},
        {"key": "", "value": 1, "spawn_cooldown": 12, "script": "turret_effect.gd"},
    ]
    for s in samples:
        entry = classify_effect(s)
        assert entry is not None, s
        assert entry["category"] in CATEGORIES, s
