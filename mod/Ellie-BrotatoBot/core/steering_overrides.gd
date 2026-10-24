extends Reference
# Pure plan-to-row translation. Character mechanics stay in WorldView.

const PlanFile = preload("plan_file.gd")


static func from_plan(loaded, character_id) -> Dictionary:
	if typeof(loaded) != TYPE_DICTIONARY or loaded.character_id != str(character_id):
		return {}
	return loaded.plan.get("steering", {})


static func resolve(row: Dictionary, overrides: Dictionary) -> Dictionary:
	var out = row.duplicate(true)
	var valid = PlanFile.valid_steering(overrides)
	for k in valid:
		out[k] = valid[k]
	if valid.has("gold_value"):
		out["gold"] = float(valid.gold_value)
	out["gold_value"] = float(out.get("gold", 0.8))
	out["tree_value"] = float(out.get("tree_value", 0.0))
	out["sweep"] = float(out.get("sweep", 1.0))
	out["sweep_radius"] = float(out.get("sweep_radius", 420.0))
	out["stand_continuity"] = float(out.get("stand_continuity", -1.2))
	out["tree_policy"] = valid.get("tree_policy", "auto")
	if out.tree_policy == "seek" and not valid.has("tree_value"):
		out.tree_value = 4.0
	elif out.tree_policy == "preserve":
		out.tree_value = 0.0
	return out


static func event(character_id, overrides: Dictionary, row: Dictionary,
		material_value: float, caution: float) -> Dictionary:
	var values = {}
	for k in PlanFile.STEERING_TYPES:
		values[k] = row[k]
	values["material_value"] = material_value
	values["caution"] = caution
	return {"character_id": str(character_id), "overrides": overrides.duplicate(true),
		"resolved": values}
