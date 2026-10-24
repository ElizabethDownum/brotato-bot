extends Reference

# Target-only metadata. Legacy linear rewards never pass through this adapter.
# Keep fields 2/3 compatible with the arbiter's attract/held reward layouts.
# main.gd:1049-1056 attracts uncollected crates at wave end; materials take priority.
const CRATE_VALUE = 1.5
const LEGENDARY_CRATE_VALUE = 2.0
const CRATE_MATERIAL_REFERENCE_VALUE = 3.0  # quiet Well Rounded .8 * 1.5 * 2.5
const LOOT_TARGET_VALUE = 8.0    # looter_stats.tres: gold value; drops require a kill


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
		and r[4] in ["floor_drop", "crate", "food", "tree", "loot"]


static func loot(unit, enabled_value: float, body_radius: float = 20.0) -> Array:
	if not is_instance_valid(unit) or not unit.is_loot or unit.dead or unit._pending_die \
			or enabled_value <= 0.0:
		return []
	var r = reward(unit.position, LOOT_TARGET_VALUE, false, "loot", unit.get_instance_id())
	r.append(body_radius)    # contact clearance, independent of the weapon standoff
	return r


static func can_damage(weapons: Array) -> bool:
	for weapon in weapons:
		if is_instance_valid(weapon) and weapon.stats != null \
				and weapon.stats.damage > 0.0 and weapon.stats.cooldown > 0.0 \
				and weapon.stats.max_range > 0.0:
			return true
	return false


static func kind(r: Array) -> String:
	return "material" if r[4] == "floor_drop" else r[4]
