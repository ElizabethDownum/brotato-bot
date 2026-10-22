# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.scene import parse_scene_node

_SCENE = """[gd_scene load_steps=2 format=2]

[ext_resource path="res://projectiles/bullet_enemy/enemy_projectile.tscn" type="PackedScene" id=4]

[node name="Enemy" index="0"]

[node name="AttackBehavior" parent="." index="7"]
projectile_scene = ExtResource( 4 )
projectile_speed = 600
damage = 1
damage_increase_each_wave = 0.75
number_projectiles = 1
spawn_projectiles_on_target = false
"""


def test_reads_named_node_kvs():
    node = parse_scene_node(_SCENE, "AttackBehavior")
    assert node["damage"] == 1
    assert node["damage_increase_each_wave"] == 0.75
    assert node["number_projectiles"] == 1
    assert node["projectile_speed"] == 600
    assert node["spawn_projectiles_on_target"] is False
    assert node["projectile_scene"] == {"__ext__": 4}


def test_missing_node_returns_empty():
    assert parse_scene_node(_SCENE, "NoSuchNode") == {}


def test_stops_at_next_section():
    # "Enemy" node has no KVs before AttackBehavior begins
    assert parse_scene_node(_SCENE, "Enemy") == {}
