extends Reference
# Soft weapon-set preference (plan key prefer_sets: set id -> the set's full
# value for the goal). Autoload-free so it runs in the headless test project.
# No class_name -- callers preload this script.

const SET_WEAPONS = 6.0  # set bonuses grow per weapon held, up to a full board


# Sum over the weapon's set ids of prefer_sets[id] / 6: one sixth of the set's
# full value per weapon. Unknown sets and non-numeric values count 0.
static func bonus(set_ids: Array, prefer_sets: Dictionary) -> float:
	var total = 0.0
	for id in set_ids:
		var v = prefer_sets.get(id)
		if typeof(v) == TYPE_REAL or typeof(v) == TYPE_INT:
			total += float(v) / SET_WEAPONS
	return total
