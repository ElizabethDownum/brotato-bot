# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.achievements import (
    build_achievement_record,
    merge_achievement_records,
    parse_achievement_localizations_csv,
)

ADVANCED_TECH = """[gd_resource type="Resource" load_steps=4 format=2]

[ext_resource path="res://items/all/exoskeleton/exoskeleton_icon.png" type="Texture" id=1]
[ext_resource path="res://items/characters/cyborg/cyborg_data.tres" type="Resource" id=2]
[ext_resource path="res://challenges/global/challenge_data.gd" type="Script" id=3]

[resource]
script = ExtResource( 3 )
my_id = "chal_advanced_technology"
name = "CHAL_ADVANCED_TECHNOLOGY"
value = 10
description = "CHAL_ADVANCED_TECHNOLOGY_DESC"
reward_type = 6
reward = ExtResource( 2 )
stat = "stat_ranged_damage"
additional_args = [ 3 ]
"""

APPRENTICE = """[gd_resource type="Resource" load_steps=4 format=2]

[ext_resource path="res://items/characters/apprentice/apprentice_icon.png" type="Texture" id=1]
[ext_resource path="res://weapons/melee/fighting_stick/1/fighting_stick_data.tres" type="Resource" id=2]
[ext_resource path="res://challenges/global/challenge_data.gd" type="Script" id=3]

[resource]
script = ExtResource( 3 )
my_id = "chal_apprentice"
name = "CHARACTER_APPRENTICE"
value = 1
description = "CHAL_CHARACTER_DESC"
reward_type = 1
reward = ExtResource( 2 )
stat = ""
additional_args = [  ]
"""

ARMS_DEALER = """[gd_resource type="Resource" load_steps=3 format=2]

[ext_resource path="res://items/all/anvil/anvil_data.tres" type="Resource" id=1]
[ext_resource path="res://challenges/global/challenge_data.gd" type="Script" id=2]

[resource]
script = ExtResource( 2 )
my_id = "chal_arms_dealer"
value = 1
reward_type = 0
reward = ExtResource( 1 )
stat = ""
additional_args = [  ]
"""

LOC_CSV = """name,locale,lockedTitle,lockedDescription,unlockedTitle,unlockedDescription,flavorText,lockedIcon,unlockedIcon
chal_advanced_technology,default,Advanced Technology,"Reach 10 Ranged Damage and get 3 structures at the same time",Advanced Technology,"Reach 10 Ranged Damage and get 3 structures at the same time",,a.jpg,b.jpg
chal_advanced_technology,fr,Technologie Avancée,"Atteignez 10 Dégâts à Distance",Technologie Avancée,"Atteignez 10 Dégâts à Distance",,a.jpg,b.jpg
chal_apprentice,default,Apprentice,"Win a run with Apprentice",Apprentice,"Win a run with Apprentice",,a.jpg,b.jpg
chal_druid,default,Druid,"Win a run with Druid",Druid,"Win a run with Druid",,a.jpg,b.jpg
"""


def test_stat_threshold_achievement_resolves_character_reward():
    rec = build_achievement_record(ADVANCED_TECH)
    assert rec["id"] == "chal_advanced_technology"
    assert rec["stat"] == "stat_ranged_damage"
    assert rec["value"] == 10
    assert rec["additional_args"] == [3]
    assert rec["reward_type"] == "CHARACTER"
    assert rec["reward_id"] == "character_cyborg"


def test_weapon_reward_resolves_weapon_id_dropping_tier():
    rec = build_achievement_record(APPRENTICE)
    assert rec["reward_type"] == "WEAPON"
    assert rec["reward_id"] == "weapon_fighting_stick"
    assert rec["stat"] is None


def test_item_reward_resolves_item_id():
    rec = build_achievement_record(ARMS_DEALER)
    assert rec["reward_type"] == "ITEM"
    assert rec["reward_id"] == "item_anvil"


def test_unrecognized_reward_type_is_null_not_mislabeled_as_item():
    text = ARMS_DEALER.replace("reward_type = 0", "reward_type = 99")
    rec = build_achievement_record(text)
    assert rec["reward_type"] is None


def test_parse_achievement_localizations_csv_groups_by_id_and_locale():
    loc = parse_achievement_localizations_csv(LOC_CSV)
    assert set(loc["chal_advanced_technology"]) == {"default", "fr"}
    assert loc["chal_advanced_technology"]["default"]["unlocked_title"] == "Advanced Technology"
    assert loc["chal_advanced_technology"]["fr"]["locked_description"] == "Atteignez 10 Dégâts à Distance"


def test_merge_filters_out_ids_missing_from_localization_csv():
    # chal_arms_dealer has a .tres but no row in this loc CSV fixture -> dropped,
    # mirroring how challenge_service.gd reuses ChallengeData for non-achievement
    # unlocks that never made it into the Steam achievement export.
    tres_records = [
        build_achievement_record(ADVANCED_TECH),
        build_achievement_record(APPRENTICE),
        build_achievement_record(ARMS_DEALER),
    ]
    loc_by_id = parse_achievement_localizations_csv(LOC_CSV)
    merged = merge_achievement_records(tres_records, loc_by_id)

    ids = {r["id"] for r in merged}
    assert ids == {"chal_advanced_technology", "chal_apprentice", "chal_druid"}


def test_merge_keeps_loc_only_entry_with_null_fields_when_tres_missing():
    loc_by_id = parse_achievement_localizations_csv(LOC_CSV)
    merged = merge_achievement_records([build_achievement_record(ADVANCED_TECH)], loc_by_id)

    druid = next(r for r in merged if r["id"] == "chal_druid")
    assert druid["has_tres"] is False
    assert druid["stat"] is None
    assert druid["reward_id"] is None
    assert druid["localized"]["default"]["unlocked_title"] == "Druid"


def test_merge_attaches_localized_text_to_tres_backed_record():
    loc_by_id = parse_achievement_localizations_csv(LOC_CSV)
    merged = merge_achievement_records([build_achievement_record(ADVANCED_TECH)], loc_by_id)

    rec = next(r for r in merged if r["id"] == "chal_advanced_technology")
    assert rec["has_tres"] is True
    assert rec["localized"]["default"]["unlocked_title"] == "Advanced Technology"
    assert rec["localized"]["fr"]["locked_description"] == "Atteignez 10 Dégâts à Distance"
