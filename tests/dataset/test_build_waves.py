# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.waves import build_wave_record, enemy_id_from_unit_scene

_WAVE = '''[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://zones/wave_data.gd" type="Script" id=1]
[ext_resource path="res://zones/zone_1/020/group_2.tres" type="Resource" id=4]
[resource]
script = ExtResource( 1 )
wave_duration = 90
max_enemies = 100
groups_data = [ ExtResource( 4 ) ]
conditional_groups_data = [  ]
'''

_GROUP = '''[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://zones/wave_group_data.gd" type="Script" id=1]
[ext_resource path="res://zones/zone_1/020/unit_3.tres" type="Resource" id=2]
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
'''

_UNIT = '''[gd_resource type="Resource" load_steps=3 format=2]
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
'''


def test_enemy_id_from_scene_name():
    assert enemy_id_from_unit_scene("baby_alien.tscn") == "baby_alien"


def test_wave_record_resolves_groups_units():
    rec = build_wave_record(_WAVE, [_GROUP], {"group_2.tres": [_UNIT]}, wave=20)
    assert rec["wave"] == 20
    assert rec["wave_duration"] == 90
    assert rec["max_enemies"] == 100
    assert len(rec["groups"]) == 1
    g = rec["groups"][0]
    assert g["enemy_id"] == "baby_alien"
    assert g["base_count"] == [5, 5]
    assert g["first_spawn_s"] == 1
    assert g["repeats"] == 5
    assert g["repeat_interval"] == 3
    assert g["min_danger"] == 0
    assert g["is_boss"] is False
