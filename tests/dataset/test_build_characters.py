# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.characters import build_character_record
from brotato_bot.dataset.spud.builders.sets import build_set_record

RANGER_DATA = """[gd_resource type="Resource" format=2]
[resource]
tier = 0
"""

EFF_FLAT_RANGE = '[resource]\nkey = "stat_range"\nvalue = 50\neffect_sign = 3\n'
EFF_RD_GAIN = '[resource]\nkey = "effect_increase_stat_gains"\nvalue = 50\nstats_modified = [ "stat_ranged_damage" ]\n'
EFF_HP_GAIN = '[resource]\nkey = "effect_reduce_stat_gains"\nvalue = -25\nstats_modified = [ "stat_max_hp" ]\n'
EFF_NO_MELEE = '[resource]\nkey = "no_melee_weapons"\nvalue = 1\n'


def test_ranger_gain_modifiers():
    rec = build_character_record(
        RANGER_DATA, [EFF_FLAT_RANGE, EFF_RD_GAIN, EFF_HP_GAIN, EFF_NO_MELEE],
        char_id="character_ranger", name="Ranger",
        wanted_tags=["stat_ranged_damage", "stat_range"],
        banned_item_groups=["melee_damage"],
    )
    assert {"stat": "stat_ranged_damage", "pct": 50} in rec["gain_modifiers"]
    assert {"stat": "stat_max_hp", "pct": -25} in rec["gain_modifiers"]
    assert {"stat": "stat_range", "value": 50} in rec["flat_bonuses"]
    assert "no_melee_weapons" in rec["special_effects"]


def test_set_bonuses_sorted_by_count():
    set_data = '[gd_resource type="Resource" format=2]\n[resource]\nmy_id = "set_gun"\n'
    eff2 = '[resource]\nkey = "stat_range"\nvalue = 5\n'
    eff6 = '[resource]\nkey = "stat_range"\nvalue = 50\n'
    rec = build_set_record(set_data, {6: eff6, 2: eff2}, set_id="set_gun", name="Gun")
    assert [b["count"] for b in rec["bonuses"]] == [2, 6]
    assert rec["bonuses"][1]["effect"] == {"key": "stat_range", "value": 50}


def test_starting_weapon_grant_excluded_from_special_effects():
    from brotato_bot.dataset.spud.builders.characters import build_character_record
    data = '[gd_resource type="Resource" format=2]\n[resource]\ntier = 0\n'
    weapon_grant = '[resource]\nkey = "weapon_pistol_1"\nvalue = 1\n'
    no_melee = '[resource]\nkey = "no_melee_weapons"\nvalue = 1\n'
    rec = build_character_record(data, [weapon_grant, no_melee], char_id="c", name="C",
                                 wanted_tags=[], banned_item_groups=[])
    assert "no_melee_weapons" in rec["special_effects"]
    assert "weapon_pistol_1" not in rec["special_effects"]


def test_character_record_falls_back_to_slug_name_without_translations():
    data = '[gd_resource type="Resource" format=2]\n[resource]\ntier = 0\nname = "CHAR_X"\n'
    rec = build_character_record(data, [], char_id="character_x", name="X",
                                 wanted_tags=[], banned_item_groups=[])
    assert rec["display_name"] == "X"
    assert rec["description"] == ""


def test_character_record_resolves_display_name_with_translations():
    data = '[gd_resource type="Resource" format=2]\n[resource]\ntier = 0\nname = "CHAR_X"\n'
    rec = build_character_record(data, [], char_id="character_x", name="X",
                                 wanted_tags=[], banned_item_groups=[],
                                 tr={"CHAR_X": "X (EN)"})
    assert rec["display_name"] == "X (EN)"


def test_set_record_falls_back_to_slug_name_without_translations():
    set_data = '[gd_resource type="Resource" format=2]\n[resource]\nname = "SET_GUN"\n'
    eff2 = '[resource]\nkey = "stat_range"\nvalue = 5\n'
    rec = build_set_record(set_data, {2: eff2}, set_id="set_gun", name="Gun")
    assert rec["display_name"] == "Gun"
    assert rec["description"] == ""


EFF_CLASS_BONUS_PRECISE = (
    '[resource]\nkey = "effect_weapon_class_bonus"\nvalue = 100\n'
    'set_id = "set_precise"\nstat_displayed_name = "stat_range"\n'
    'stat_name = "max_range"\n'
)
EFF_CLASS_BONUS_UPPER = (
    '[resource]\nkey = "EFFECT_WEAPON_CLASS_BONUS"\nvalue = 50\n'
    'set_id = "set_unarmed"\nstat_displayed_name = "stat_attack_speed"\n'
    'stat_name = "attack_speed_mod"\n'
)


def test_class_bonus_captured_structurally():
    rec = build_character_record(
        RANGER_DATA, [EFF_CLASS_BONUS_PRECISE],
        char_id="character_crazy", name="Crazy",
        wanted_tags=[], banned_item_groups=[],
        set_names={"set_precise": "Precise"})
    assert rec["class_bonuses"] == [{
        "set_id": "set_precise", "set_name": "Precise",
        "stat": "max_range", "stat_displayed": "stat_range", "value": 100}]
    # the lowercase-key token is structured out of special_effects
    assert "effect_weapon_class_bonus" not in rec["special_effects"]


def test_class_bonus_token_absent_from_special_effects_uppercase_key():
    rec = build_character_record(
        RANGER_DATA, [EFF_CLASS_BONUS_UPPER],
        char_id="character_brawler", name="Brawler",
        wanted_tags=[], banned_item_groups=[])
    assert rec["special_effects"] == []
    assert rec["class_bonuses"][0]["set_id"] == "set_unarmed"
    assert rec["class_bonuses"][0]["value"] == 50


def test_class_bonus_set_name_falls_back_to_titlecased_id():
    rec = build_character_record(
        RANGER_DATA, [EFF_CLASS_BONUS_PRECISE],
        char_id="c", name="C", wanted_tags=[], banned_item_groups=[])
    assert rec["class_bonuses"][0]["set_name"] == "Precise"


def test_non_class_character_has_empty_class_bonuses():
    rec = build_character_record(
        RANGER_DATA, [EFF_FLAT_RANGE], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[])
    assert rec["class_bonuses"] == []


# starting_weapons is the run-start SELECTION POOL the weapon-selection menu
# offers (ui/menus/run/weapon_selection.gd:92), not a fixed starting weapon.
WEAPONS_BY_ID = {
    "weapon_wrench": {"name": "Wrench", "display_name": "Wrench", "weapon_type": "melee"},
    "weapon_knife": {"name": "Knife", "display_name": "Knife", "weapon_type": "melee"},
    "weapon_pistol": {"name": "Pistol", "display_name": "Pistol", "weapon_type": "ranged"},
    # `name` is the slug-titlecased fallback; `display_name` is the localized
    # in-game text, and the two diverge for 7 weapons (Smg -> SMG,
    # Cactus Mace -> Cacti Club, Fighting Stick -> Quarterstaff, ...).
    "weapon_smg": {"name": "Smg", "display_name": "SMG", "weapon_type": "ranged"},
}

POOL_DATA = """[gd_resource type="Resource" load_steps=5 format=2]
[ext_resource path="res://weapons/ranged/pistol/1/pistol_data.tres" type="Resource" id=1]
[ext_resource path="res://weapons/melee/wrench/1/wrench_data.tres" type="Resource" id=2]
[ext_resource path="res://weapons/ranged/smg/1/smg_data.tres" type="Resource" id=3]
[ext_resource path="res://weapons/melee/knife/1/knife_data.tres" type="Resource" id=4]
[resource]
tier = 0
starting_weapons = [ ExtResource( 1 ), ExtResource( 2 ), ExtResource( 3 ), ExtResource( 4 ) ]
"""


def test_starting_weapon_pool_resolves_to_weapon_names():
    rec = build_character_record(
        POOL_DATA, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[], weapons_by_id=WEAPONS_BY_ID)
    assert set(rec["starting_weapon_pool"]) == {"Pistol", "Wrench", "SMG", "Knife"}


def test_starting_weapon_pool_uses_localized_display_name():
    rec = build_character_record(
        POOL_DATA, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[], weapons_by_id=WEAPONS_BY_ID)
    assert "SMG" in rec["starting_weapon_pool"]
    assert "Smg" not in rec["starting_weapon_pool"]


def test_starting_weapon_pool_orders_melee_before_ranged():
    # Mirrors item_service.gd:1043 get_ordered_starting_weapons, which the
    # selection menu applies before display: all melee, then all ranged.
    rec = build_character_record(
        POOL_DATA, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[], weapons_by_id=WEAPONS_BY_ID)
    assert rec["starting_weapon_pool"] == ["Wrench", "Knife", "Pistol", "SMG"]


def test_starting_weapon_pool_skips_unresolvable_reference():
    data = POOL_DATA.replace("weapons/melee/wrench/1/wrench_data.tres",
                             "weapons/melee/nonexistent/1/nonexistent_data.tres")
    rec = build_character_record(
        data, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[], weapons_by_id=WEAPONS_BY_ID)
    assert rec["starting_weapon_pool"] == ["Knife", "Pistol", "SMG"]


def test_starting_weapon_pool_empty_when_character_has_none():
    # Beast Master and Bull genuinely start with no weapon — empty is valid data.
    rec = build_character_record(
        RANGER_DATA, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[], weapons_by_id=WEAPONS_BY_ID)
    assert rec["starting_weapon_pool"] == []


def test_starting_weapon_pool_empty_without_weapon_map():
    rec = build_character_record(
        POOL_DATA, [], char_id="c", name="C",
        wanted_tags=[], banned_item_groups=[])
    assert rec["starting_weapon_pool"] == []
