# Proposal 1

## Target
<One or two sentences: the target challenge id, or "any locked character", and why it is next.>

## Next run
- character: <character_id>
- danger: <n>
- target: <challenge id or none>
- starting_weapon: <weapon id from the fit's top choice, or any>

## Plan
```json
{
  "plan_id": "<plan_id, for example well-rounded-v1>",
  "character_id": "<character_id>",
  "plan": {
    "steering": {},
    "weapon_type": "any",
    "weapon_set": "",
    "stats": {
      "stat_percent_damage": 6.0,
      "stat_attack_speed": 5.0,
      "stat_max_hp": 5.0,
      "stat_ranged_damage": 4.0,
      "stat_melee_damage": 4.0,
      "stat_armor": 4.0,
      "stat_crit_chance": 4.0,
      "stat_lifesteal": 4.0,
      "stat_dodge": 3.0,
      "stat_harvesting": 5.0,
      "stat_hp_regeneration": 2.0,
      "stat_range": 2.0
    },
    "item_bonus": {},
    "phase_boost": {},
    "harvest_cap": 40,
    "max_weapons": 6,
    "reroll_keep": 5,
    "max_rerolls": 15,
    "gold_floor": 0,
    "min_buy": 2.0,
    "prefer_weapons": [],
    "ban_items": [],
    "deprioritize_weapons": [],
    "ask_on": [],
    "unique_weapons": false,
    "stack_combine": false,
    "hitrate_pref": false,
    "spend_surplus": false
  }
}
```

## Why
<At most three sentences. Each cites a file or a dataset fact, for example "unlock_state.json: chal_x value 5, open".>

## Risk
<One to three sentences: what could make this run waste its time.>

## Stagnation check
<The line printed by the stagnation command, copied verbatim.>
