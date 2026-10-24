# Checkpoint 20261023-233317-apprentice-d0 wave 10

## Achieved

- Target challenge: chal_dying
- Challenges completed this run: chal_dying
- Wave 10, HP 31/31, gold 210

## Remaining potential

- Weapons: weapon_double_barrel_shotgun_2, weapon_pistol_3, weapon_double_barrel_shotgun_2, weapon_pistol_3, weapon_laser_gun_2, weapon_laser_gun_2
- Items: character_apprentice x1, item_turret x1, item_ratzilla x1, item_broken_mouth x3, item_coffee x1, item_pile_of_books x1, item_handcuffs x1, item_poisonous_tonic x1
- Stats: stat_attack_speed 35, stat_crit_chance 13, stat_dodge 9, stat_elemental_damage 20, stat_engineering 15, stat_hp_regeneration -5, stat_lifesteal 2, stat_max_hp 31, stat_melee_damage 32, stat_percent_damage -2, stat_range 65, stat_ranged_damage 25
- Plan in effect: apprentice-dying-v1

## Plan revision

`revise_plan` (confidence 0.6) with this proposed plan patch; the run's checkpoint event records whether the mod applied it:

```json
{
  "stats": {
    "stat_max_hp": 10,
    "stat_attack_speed": 8,
    "stat_dodge": 7,
    "stat_ranged_damage": 6,
    "stat_armor": 6,
    "stat_percent_damage": 5,
    "stat_crit_chance": 5,
    "stat_lifesteal": 4,
    "stat_hp_regeneration": 3
  },
  "item_bonus": {},
  "ask_on": []
}
```

## Rationale

chal_dying is done, so the negative regen weight and the self-damage item bonuses no longer help. Value regen positively and drop the dying-specific bonuses. Keep the survival and offense stats for the remaining waves.
