# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.items import build_item_record

HANDCUFFS_DATA = """[gd_resource type="Resource" format=2]
[resource]
tier = 2
value = 80
tags = [ "stat_melee_damage", "stat_ranged_damage", "stat_elemental_damage" ]
"""

EFF_MELEE = '[resource]\nkey = "stat_melee_damage"\nvalue = 8\neffect_sign = 3\ntext_key = ""\n'
EFF_RANGED = '[resource]\nkey = "stat_ranged_damage"\nvalue = 8\neffect_sign = 3\ntext_key = ""\n'
EFF_ELEM = '[resource]\nkey = "stat_elemental_damage"\nvalue = 8\neffect_sign = 3\ntext_key = ""\n'
EFF_CAP = '[resource]\nkey = "hp_cap"\nvalue = 0\neffect_sign = 0\ntext_key = "EFFECT_HP_CAP_AT_CURRENT_VALUE"\n'


def test_item_effects_parsed():
    rec = build_item_record(HANDCUFFS_DATA, [EFF_MELEE, EFF_RANGED, EFF_ELEM, EFF_CAP],
                            item_id="item_handcuffs", name="Handcuffs")
    assert rec["value"] == 80
    assert {"key": "stat_ranged_damage", "value": 8, "effect_sign": 3, "text_key": "",
            "text": ""} in rec["effects"]
    assert rec["damage_tags"] == ["stat_melee_damage", "stat_ranged_damage", "stat_elemental_damage"]


def test_item_cap_archetype_detected():
    rec = build_item_record(HANDCUFFS_DATA, [EFF_MELEE, EFF_RANGED, EFF_ELEM, EFF_CAP],
                            item_id="item_handcuffs", name="Handcuffs")
    assert "cap_at_current_value" in rec["archetype"]
    assert rec["frozen_stat"] == "stat_max_hp"


DATA_LOC = ('[gd_resource type="Resource" format=2]\n[resource]\n'
            'name = "ITEM_HANDCUFFS"\ndescription = "ITEM_HANDCUFFS_DESC"\n'
            'tier = 2\nvalue = 40\ntags = [ "stat_ranged_damage" ]\n')
EFF_TR = '[resource]\nkey = "hp_cap"\nvalue = 0\neffect_sign = 0\ntext_key = "EFFECT_HP_CAP_AT_CURRENT_VALUE"\n'
ITEM_TR = {"ITEM_HANDCUFFS": "Handcuffs (EN)",
           "ITEM_HANDCUFFS_DESC": "Freezes Max HP.",
           "EFFECT_HP_CAP_AT_CURRENT_VALUE": "Max HP is capped at its current value"}


def test_item_record_resolves_display_name_description_and_effect_text():
    rec = build_item_record(DATA_LOC, [EFF_TR], item_id="item_handcuffs",
                            name="Handcuffs", tr=ITEM_TR)
    assert rec["display_name"] == "Handcuffs (EN)"
    assert rec["description"] == "Freezes Max HP."
    assert rec["effects"][0]["text"] == "Max HP is capped at its current value"


def test_item_record_falls_back_without_translations():
    rec = build_item_record(DATA_LOC, [EFF_TR], item_id="item_handcuffs",
                            name="Handcuffs")
    assert rec["display_name"] == "Handcuffs"
    assert rec["effects"][0]["text"] == ""


def test_item_tier_is_one_indexed():
    # Raw .tres tiers are 0-indexed (0-3); records must ship the 1-indexed
    # tier the game UI displays (I-IV), matching weapons and runfile.py.
    rec = build_item_record(HANDCUFFS_DATA, [], item_id="item_handcuffs",
                            name="Handcuffs")
    assert rec["tier"] == 3  # raw `tier = 2` in the fixture
