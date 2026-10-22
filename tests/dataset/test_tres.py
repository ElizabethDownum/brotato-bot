# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.tres import parse_tres

SHREDDER = """[gd_resource type="Resource" load_steps=2 format=2]

[ext_resource path="res://weapons/weapon_stats/ranged_weapon_stats.gd" type="Script" id=1]
[ext_resource path="res://projectiles/bullet_shredder/bullet_shredder.tscn" type="PackedScene" id=2]

[resource]
script = ExtResource( 1 )
cooldown = 45
damage = 25
accuracy = 1.0
crit_chance = 0.03
scaling_stats = [ [ "stat_ranged_damage", 0.5 ] ]
recoil_duration = 0.15
can_have_negative_knockback = false
projectile_scene = ExtResource( 2 )
"""


def test_parses_scalars():
    doc = parse_tres(SHREDDER)
    assert doc.resource["cooldown"] == 45
    assert doc.resource["damage"] == 25
    assert doc.resource["accuracy"] == 1.0
    assert doc.resource["can_have_negative_knockback"] is False


def test_parses_nested_array():
    doc = parse_tres(SHREDDER)
    assert doc.resource["scaling_stats"] == [["stat_ranged_damage", 0.5]]


def test_parses_ext_resource_reference():
    doc = parse_tres(SHREDDER)
    assert doc.resource["projectile_scene"] == {"__ext__": 2}
    assert doc.ext_resources[2]["path"].endswith("bullet_shredder.tscn")


def test_ignores_gd_resource_header_keys():
    doc = parse_tres(SHREDDER)
    assert "load_steps" not in doc.resource
    assert "type" not in doc.resource
