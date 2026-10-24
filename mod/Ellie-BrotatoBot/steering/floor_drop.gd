extends Reference
# Pure world-view adapter: attracted gold never steers. Face value does not
# affect the existing per-entity reward; fields 2/3 preserve the old rim rules.


static func reward(position: Vector2, gold_value: float, draw: float, instance_id: int) -> Array:
	return [position, gold_value * draw, true, 0.0, "floor_drop", instance_id]
