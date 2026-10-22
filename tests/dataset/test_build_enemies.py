# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.enemies import build_enemy_record

_BABY_STATS = '''[gd_resource type="Resource" load_steps=3 format=2]
[ext_resource path="res://entities/units/unit/stats.gd" type="Script" id=1]
[resource]
script = ExtResource( 1 )
health = 3
health_increase_each_wave = 2.0
speed = 250
speed_randomization = 50
damage = 1
damage_increase_each_wave = 0.6
attack_cd = 30.0
knockback_resistance = 0.0
armor = 0
armor_increase_each_wave = 0.0
'''

_SPITTER_SCENE = '''[gd_scene load_steps=2 format=2]
[ext_resource path="res://entities/units/enemies/attack_behaviors/shooting_attack_behavior.gd" type="Script" id=3]
[ext_resource path="res://projectiles/bullet_enemy/enemy_projectile.tscn" type="PackedScene" id=4]
[node name="Enemy" instance=ExtResource( 1 )]
[node name="AttackBehavior" parent="." index="7"]
script = ExtResource( 3 )
projectile_scene = ExtResource( 4 )
damage = 1
damage_increase_each_wave = 0.75
number_projectiles = 1
'''

_BRUISER_SCENE = '''[gd_scene load_steps=2 format=2]
[ext_resource path="res://entities/units/enemies/attack_behaviors/charging_attack_behavior.gd" type="Script" id=3]
[node name="Enemy" instance=ExtResource( 1 )]
[node name="AttackBehavior" parent="." index="7"]
script = ExtResource( 3 )
charge_speed = 700.0
'''

_SPAWNER_SCENE = '''[gd_scene load_steps=2 format=2]
[ext_resource path="res://entities/units/enemies/attack_behaviors/spawning_attack_behavior.gd" type="Script" id=3]
[node name="Enemy" instance=ExtResource( 1 )]
[node name="AttackBehavior" parent="." index="7"]
script = ExtResource( 3 )
damage = 2
damage_increase_each_wave = 0.5
number_projectiles = 1
'''

# Boss (mantis-shaped): the primary AttackBehavior node uses shooting
# (ext id 6, declared first); an auxiliary States AttackBehavior uses charging
# (ext id 8, declared last). The old scan-all/last-wins classifier collapsed
# this to "charging"; reading the primary node's own script yields "ranged".
_BOSS_SCENE = '''[gd_scene load_steps=2 format=2]
[ext_resource path="res://entities/units/enemies/attack_behaviors/shooting_attack_behavior.gd" type="Script" id=6]
[ext_resource path="res://entities/units/enemies/attack_behaviors/charging_attack_behavior.gd" type="Script" id=8]
[node name="Boss" instance=ExtResource( 1 )]
[node name="AttackBehavior" parent="." index="7"]
script = ExtResource( 6 )
damage = 3
damage_increase_each_wave = 0.5
number_projectiles = 1
[node name="AttackBehavior" parent="States/State1" index="1"]
script = ExtResource( 8 )
'''


def test_contact_enemy_base_and_slopes():
    rec = build_enemy_record(_BABY_STATS, None, enemy_id="baby_alien", name="Baby Alien")
    assert rec["id"] == "baby_alien"
    assert rec["base"]["health"] == 3
    assert rec["base"]["speed"] == 250
    assert rec["base"]["speed_randomization"] == 50
    assert rec["per_wave"]["health"] == 2.0
    assert rec["per_wave"]["damage"] == 0.6
    assert rec["per_wave"]["armor"] == 0.0
    # no attack-behavior scene -> pure contact
    assert rec["attack"]["kind"] == "melee"
    assert rec["abilities"] == []


def test_ranged_enemy_attack_profile():
    rec = build_enemy_record(_BABY_STATS, _SPITTER_SCENE, enemy_id="spitter", name="Spitter")
    assert rec["attack"]["kind"] == "ranged"
    assert rec["attack"]["projectile_damage"] == 1
    assert rec["attack"]["projectile_dmg_per_wave"] == 0.75
    assert rec["attack"]["number_projectiles"] == 1


def test_charging_enemy_kind_and_ability():
    rec = build_enemy_record(_BABY_STATS, _BRUISER_SCENE, enemy_id="bruiser", name="Bruiser")
    assert rec["attack"]["kind"] == "charging"
    assert "charger" in rec["abilities"]


def test_spawner_enemy_kind_and_ability():
    rec = build_enemy_record(_BABY_STATS, _SPAWNER_SCENE, enemy_id="spawner", name="Spawner")
    assert rec["attack"]["kind"] == "ranged"
    assert "spawner" in rec["abilities"]


def test_boss_scene_flags_bespoke_and_uses_primary_node_not_last_ext():
    rec = build_enemy_record(_BABY_STATS, _BOSS_SCENE, enemy_id="mantis", name="Mantis")
    # Primary AttackBehavior node is shooting -> ranged. The auxiliary charging
    # node (higher ext id) must NOT win; under the old last-wins scan this was
    # wrongly "charging".
    assert rec["attack"]["kind"] == "ranged"
    assert rec["attack"]["projectile_damage"] == 3
    assert "bespoke_kit_not_modeled" in rec["abilities"]
