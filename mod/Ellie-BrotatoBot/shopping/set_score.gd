extends Reference
# Soft weapon-set preference (plan key prefer_sets: set id -> score value of
# one more weapon in that set). Autoload-free for the headless test project.
# No class_name -- callers preload this script.

# Sum the per-weapon values of the weapon's sets.
# Unknown sets and non-numeric values count 0.
static func bonus(set_ids: Array, prefer_sets: Dictionary) -> float:
	var total = 0.0
	for id in set_ids:
		var v = prefer_sets.get(id)
		if typeof(v) == TYPE_REAL or typeof(v) == TYPE_INT:
			total += float(v)
	return total
