extends Reference
# One entry per live pooled life, keyed by instance id. Times are monotonic seconds
# since the wave's telemetry started, independent of the game's resettable timer;
# the run recorder adds its usual run-relative millisecond t to emitted records.

var _live = {}


func spawn(id, wave, t, distance):
	if not _live.has(id):
		_live[id] = {"wave": int(wave), "spawn_t": float(t), "closest": float(distance)}
	observe(id, distance)


func observe(id, distance):
	if _live.has(id):
		_live[id].closest = min(_live[id].closest, float(distance))


static func outcome(cleaning_up: bool, killed_by_player: bool, can_drop_loot: bool) -> String:
	if cleaning_up:
		return "wave_end"
	# The enemy-cap cull calls die() with the default killed-by-player=true,
	# but sets can_drop_loot=false first (entity_spawner.gd:164-165).
	return "killed" if killed_by_player and can_drop_loot else "culled"


func finish(id, t, result):
	if not _live.has(id):
		return null
	var event = _live[id].duplicate(true)
	_live.erase(id)
	event["alien_id"] = int(id)
	event["end_t"] = float(t)
	event["outcome"] = str(result)
	return event


func missing(ids: Array, t) -> Array:
	var events = []
	for id in _live.keys():
		if not id in ids:
			# Defensive fallback; normal cap culls emit died synchronously.
			events.append(finish(id, t, "culled"))
	return events


func finish_wave(t) -> Array:
	var events = []
	for id in _live.keys():
		events.append(finish(id, t, "wave_end"))
	return events


static func snapshot(positions: Array, origin: Vector2, steer_range: float) -> Dictionary:
	var nearest = -1.0
	for position in positions:
		var distance = origin.distance_to(position)
		if nearest < 0.0 or distance < nearest:
			nearest = distance
	return {"alive": positions.size(), "nearest": nearest,
		"in_steer_range": nearest >= 0.0 and nearest < steer_range}
