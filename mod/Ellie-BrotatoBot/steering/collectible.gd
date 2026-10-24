extends Reference

# Target-only metadata. Legacy linear rewards never pass through this adapter.
# Keep fields 2/3 compatible with the arbiter's attract/held reward layouts.
const CRATE_VALUE = 6.0
const LEGENDARY_CRATE_VALUE = 12.0


static func reward(position: Vector2, value: float, attracted: bool,
		kind: String, instance_id: int) -> Array:
	return [position, value, attracted, 0.0, kind, instance_id]


static func consumable(position: Vector2, consumable_id: String, food_value: float,
		instance_id: int) -> Array:
	var value = food_value
	var kind = "food"
	if consumable_id == "consumable_item_box":
		value = CRATE_VALUE
		kind = "crate"
	elif consumable_id == "consumable_legendary_item_box":
		value = LEGENDARY_CRATE_VALUE
		kind = "crate"
	return reward(position, value, true, kind, instance_id)


static func marked(r: Array) -> bool:
	return r.size() > 5 and float(r[3]) == 0.0 \
		and r[4] in ["floor_drop", "crate", "food", "tree"]


static func kind(r: Array) -> String:
	return "material" if r[4] == "floor_drop" else r[4]
