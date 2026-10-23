extends Reference
# Pure, magnitude-aware scoring of stat effects. No class_name and no game
# autoloads, so the headless mod tests can load it (shop_advisor.gd cannot be
# loaded there). The Python mirror is brotato_bot/run/score.py; this file is the
# source of truth.

# One unit per stat = the game's tier-1 level-up upgrade value, read from
# items/upgrades/<stat>/1/*_effect.tres (game data, 1.1.15.4).
const UNITS = {
	"stat_max_hp": 3.0,
	"stat_hp_regeneration": 2.0,
	"stat_lifesteal": 1.0,
	"stat_percent_damage": 5.0,
	"stat_melee_damage": 2.0,
	"stat_ranged_damage": 1.0,
	"stat_elemental_damage": 1.0,
	"stat_attack_speed": 5.0,
	"stat_crit_chance": 3.0,
	"stat_engineering": 2.0,
	"stat_range": 15.0,
	"stat_armor": 1.0,
	"stat_dodge": 3.0,
	"stat_speed": 3.0,
	"stat_luck": 5.0,
	"stat_harvesting": 5.0,
	"stat_accuracy": 4.0,
	"stat_crit_damage": 10.0,
	"stat_damage": 1.0,
}

# No single effect counts for more than a tier-4 upgrade (4 units).
const MAX_UNITS = 4.0


# effects: Objects (in-game Effect) or Dictionaries with .key / .value.
# weights: stat key -> priority per unit. A tier-1 level-up of a stat scores
# exactly its weight; a negative value subtracts.
static func score(effects, weights, boost_stats, harvest_capped):
	var s = 0.0
	for e in effects:
		if e == null:
			continue
		var key = e.key
		if not weights.has(key):
			continue
		var v = float(e.value)
		if v == 0.0:
			continue
		var w = float(weights[key])
		if boost_stats.has(key):
			w *= float(boost_stats[key])
		if key == "stat_harvesting" and harvest_capped:
			w *= 0.15
		var units = min(abs(v) / float(UNITS.get(key, 1.0)), MAX_UNITS)
		s += (1.0 if v > 0.0 else -1.0) * w * units
	return s
