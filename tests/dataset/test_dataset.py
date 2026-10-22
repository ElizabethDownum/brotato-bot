# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
import re

import pytest

from brotato_bot.dataset.spud import dataset
from brotato_bot.dataset.spud.builders.mechanics import STAT_MECHANICS


def test_mechanics_known_facts():
    assert STAT_MECHANICS["stat_attack_speed"]["never_dead_weight"] is True
    assert STAT_MECHANICS["stat_hp_regeneration"]["safe_at_zero"] is True
    assert STAT_MECHANICS["stat_curse"]["avoid_positive"] is True
    assert STAT_MECHANICS["stat_max_hp"]["cap"] == {"cap_key": "hp_cap"}


def test_assemble_and_validate_ok():
    weapon = {
        "id": "w", "name": "W", "tier": 4, "weapon_type": "ranged",
        "base_damage": 25, "cooldown": 45,
        "accuracy": 1.0, "crit_chance": 0.03, "crit_damage": 2.0, "piercing": 3,
        "nb_projectiles": 1, "scaling_stats": [], "can_have_negative_knockback": False,
        "base_knockback": 0, "sets": [], "effects": [], "source": "base",
    }
    item = {"id": "i", "name": "I", "tier": 0, "value": 10, "tags": [], "effects": [],
            "archetype": [], "frozen_stat": None, "scaling_stats": [], "damage_tags": [],
            "source": "base"}
    ds = dataset.assemble_dataset(game_version="1.1.0.0", generated_at="2026-07-01T00:00:00Z",
                                  weapons=[weapon], items=[item], characters=[], sets=[],
                                  enemies=[], zone_1_waves=[])
    assert ds["schema_version"] == dataset.DATASET_VERSION
    assert ds["game_version"] == "1.1.0.0"
    assert dataset.validate_dataset(ds) == []


def test_validate_flags_bad_tier():
    ds = dataset.assemble_dataset(game_version="x", generated_at="t",
                                  weapons=[{"id": "w", "tier": 9, "dps_slope_per_rd": 1.0}],
                                  items=[], characters=[], sets=[],
                                  enemies=[], zone_1_waves=[])
    problems = dataset.validate_dataset(ds)
    assert any("tier" in p for p in problems)


def test_validate_flags_missing_class_bonuses():
    ds = dataset.assemble_dataset(
        game_version="x", generated_at="t", weapons=[], items=[],
        characters=[{"id": "character_x", "gain_modifiers": []}],  # no class_bonuses
        sets=[], enemies=[], zone_1_waves=[])
    problems = dataset.validate_dataset(ds)
    assert any("class_bonuses" in p for p in problems)


def test_validate_flags_missing_starting_weapon_pool():
    ds = dataset.assemble_dataset(
        game_version="x", generated_at="t", weapons=[], items=[],
        characters=[{"id": "character_x", "gain_modifiers": [], "class_bonuses": []}],
        sets=[], enemies=[], zone_1_waves=[])
    problems = dataset.validate_dataset(ds)
    assert any("starting_weapon_pool" in p for p in problems)


def test_validate_accepts_empty_starting_weapon_pool():
    # Beast Master and Bull genuinely offer no starting weapon.
    ds = dataset.assemble_dataset(
        game_version="x", generated_at="t", weapons=[], items=[],
        characters=[{"id": "character_bull", "gain_modifiers": [], "class_bonuses": [],
                     "starting_weapon_pool": [], "source": "base"}],
        sets=[], enemies=[], zone_1_waves=[])
    assert dataset.validate_dataset(ds) == []


def test_load_missing_dataset_message(tmp_path):
    with pytest.raises(FileNotFoundError, match=re.escape("build_dataset.py")):
        dataset.load_dataset(str(tmp_path / "nope.json"))


def _minimal(**over):
    base = {"game_version": "1.1.15.4", "generated_at": "x", "weapons": [], "items": [],
            "characters": [], "sets": [], "enemies": [], "zone_1_waves": []}
    base.update(over)
    return dataset.assemble_dataset(**base)


def test_schema_version_is_8():
    assert _minimal()["schema_version"] == 8


def test_content_sources_defaults_to_base_when_empty():
    assert _minimal()["content_sources"] == ["base"]


def test_content_sources_reflects_record_sources():
    ds = _minimal(
        weapons=[{"id": "w", "name": "W", "tier": 1, "weapon_type": "ranged",
                  "base_damage": 5, "cooldown": 60, "source": "base"}],
        items=[{"id": "i", "name": "I", "effects": [], "source": "abyssal_terrors"}])
    assert ds["content_sources"] == ["abyssal_terrors", "base"]


def test_validate_flags_missing_source():
    ds = _minimal(enemies=[{"id": "baby_alien", "name": "Baby Alien"}])  # no source
    problems = dataset.validate_dataset(ds)
    assert any("source" in p for p in problems)


def test_aggregate_unmodeled_effects_buckets_by_source():
    ds = _minimal(
        weapons=[{"id": "w", "name": "W", "tier": 1, "weapon_type": "ranged",
                  "base_damage": 5, "cooldown": 60, "source": "abyssal_terrors",
                  "unmodeled_effects": ["mystery_curse", "mystery_curse", "abyssal_x"]}])
    agg = dataset.aggregate_unmodeled_effects(ds)
    assert agg == {"abyssal_terrors": ["abyssal_x", "mystery_curse"]}


def test_aggregate_unmodeled_effects_empty_when_all_modeled():
    assert dataset.aggregate_unmodeled_effects(_minimal()) == {}


def test_validate_flags_missing_weapon_type():
    ds = _minimal(weapons=[{"id": "w", "name": "W", "tier": 1}])  # no weapon_type
    problems = dataset.validate_dataset(ds)
    assert any("weapon_type" in p for p in problems)


def test_validate_flags_missing_calculation_fields():
    # base_damage and cooldown feed the DPS engine directly; a weapon without
    # them would crash calc at query time, so the validator must reject it.
    ds = _minimal(weapons=[{"id": "w", "name": "W", "tier": 1,
                            "weapon_type": "ranged"}])
    problems = dataset.validate_dataset(ds)
    assert any("base_damage" in p for p in problems)
    assert any("cooldown" in p for p in problems)


def test_validate_flags_unknown_weapon_type():
    ds = _minimal(weapons=[{"id": "w", "name": "W", "tier": 1,
                            "weapon_type": "gun",
                            "base_damage": 5, "cooldown": 60}])
    problems = dataset.validate_dataset(ds)
    assert any("weapon_type" in p for p in problems)


def test_enemies_and_waves_present_in_output():
    ds = _minimal(enemies=[{"id": "baby_alien", "name": "Baby Alien", "source": "base"}],
                  zone_1_waves=[{"wave": 1, "groups": [{"enemy_id": "baby_alien"}], "source": "base"}])
    assert ds["enemies"][0]["id"] == "baby_alien"
    assert ds["zone_1_waves"][0]["wave"] == 1
    assert dataset.validate_dataset(ds) == []


def test_validate_flags_dangling_enemy_reference():
    ds = _minimal(enemies=[{"id": "baby_alien", "name": "Baby Alien"}],
                  zone_1_waves=[{"wave": 1, "groups": [{"enemy_id": "ghost_unknown"}]}])
    problems = dataset.validate_dataset(ds)
    assert any("ghost_unknown" in p for p in problems)
