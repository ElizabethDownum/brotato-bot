extends "res://mod/tests/test_base.gd"

const Arbiter = preload("res://mod/Ellie-BrotatoBot/steering/arbiter.gd")
const Collectible = preload("res://mod/Ellie-BrotatoBot/steering/collectible.gd")
const FloorDrop = preload("res://mod/Ellie-BrotatoBot/steering/floor_drop.gd")
const ORIGIN = Vector2(1500, 1500)
const FAR = Vector2(4000, 4000)
const SPEED = 300.0
const RIM = 60.0


class LootUnit extends Reference:
	var position = ORIGIN + Vector2(700, 0)
	var is_loot = true
	var dead = false
	var _pending_die = false


func _material(offset: Vector2, id: int, value: float = 3.0) -> Array:
	return FloorDrop.reward(ORIGIN + offset, value, 1.0, id)


func _choose(arb, pos: Vector2, drops: Array, enemies: Array = [], threats: Array = [],
		weapon_range: float = 300.0) -> Vector2:
	var local = []
	for r in drops:
		if pos.distance_to(r[0]) < 900.0:
			local.append(r)
	return arb.choose(pos, SPEED, 20.0, FAR, threats, local, [], [], weapon_range, false, 100.0, 1.0,
		{"drop_pull": "target", "drop_quiet": enemies.empty(), "pickup_radius": RIM,
		"target_collectibles": drops, "target_enemies": enemies})


func _contact(at: Vector2, velocity: Vector2, damage: float = 10.0) -> Array:
	return [at, velocity, 25.0, damage, Arbiter.KIND_CONTACT, 0.0, 1.0, 1000.0]


func test_whole_map_material_1500_px_moves_toward_it():
	# Baseline reward .8, without either quiet multiplier: tests the weakest
	# ordinary material pull, not only the sweep-boosted ring fixture.
	var arb = Arbiter.new()
	var direction = _choose(arb, ORIGIN, [_material(Vector2(1500, 0), 1, 0.8)])
	assert_eq(arb._drop_target_id, 1)
	assert_eq(arb.last_target_dist, 1500.0)
	assert_true(direction.x > 0.9, "far material overcomes the standing continuity bonus")
	print("FAR_TARGET dir=%s dtg=%.1f score=%.6f" % [str(direction), arb.last_target_dist, arb.last_scores[arb.last_best_index]])


func test_material_beats_equally_distant_crates_and_crates_win_only_below_crossover():
	var material = _material(Vector2(300, 0), 1)
	var crate = Collectible.consumable(ORIGIN + Vector2(0, 300), "consumable_item_box", 0.0, 2)
	var legendary = Collectible.consumable(crate[0], "consumable_legendary_item_box", 0.0, 3)
	for box in [crate, legendary]:
		var arb = Arbiter.new()
		_choose(arb, ORIGIN, [box, material])
		assert_eq(arb._drop_target_id, 1, "material beats either crate at the same distance")
		var crossover = 300.0 * box[1] / material[1]
		box[0] = ORIGIN + Vector2(0, crossover)
		var tied = Arbiter.new()
		_choose(tied, ORIGIN, [material, box])
		assert_eq(tied._drop_target_id, 1, "earlier material wins an exact rank tie")
		box[0] = ORIGIN + Vector2(0, crossover - 1.0)
		var closer = Arbiter.new()
		_choose(closer, ORIGIN, [material, box])
		assert_eq(closer._drop_target_id, box[5], "crate wins only below its crossover")
		box[0] = ORIGIN + Vector2(0, 300)
	var ranked = Arbiter.new()
	_choose(ranked, ORIGIN, [crate, legendary])
	assert_eq(ranked._drop_target_id, 3)
	var solo = Arbiter.new()
	_choose(solo, ORIGIN, [crate])
	assert_eq(solo.last_target_kind, "crate", "crate alone is still a valid target")
	print("CRATE_CROSSOVER material=300 value=3 normal_value=%.1f crossover=150 legendary_value=%.1f crossover=200" % [Collectible.CRATE_VALUE, Collectible.LEGENDARY_CRATE_VALUE])


func test_crates_stay_below_materials_without_quiet_multipliers():
	for value in [0.8, 1.2, 3.0]:
		var material = _material(Vector2(300, 0), 1, value)
		for consumable_id in ["consumable_item_box", "consumable_legendary_item_box"]:
			var crate = Collectible.consumable(ORIGIN + Vector2(0, 300), consumable_id, 0.0, 2)
			var arb = Arbiter.new()
			_choose(arb, ORIGIN, [crate, material])
			assert_eq(arb._drop_target_id, 1, "even a .8 material outranks an equally distant crate")
			crate[0] = ORIGIN + Vector2(0, 140)
			var closer = Arbiter.new()
			_choose(closer, ORIGIN, [crate, material])
			assert_eq(closer._drop_target_id, 2, "a clearly closer crate still wins")


func test_fruit_uses_resolved_food_value_and_nonpositive_is_never_target():
	# Default _food_value is min(FOOD_MAX=12, missing_hp). WorldView still
	# resolves character-specific modes before passing this scalar unchanged.
	for missing_hp in [12.0, 0.0, -0.8]:
		var food = Collectible.consumable(ORIGIN + Vector2(0, 300), "consumable_fruit", missing_hp, 2)
		var arb = Arbiter.new()
		_choose(arb, ORIGIN, [_material(Vector2(300, 0), 1), food])
		assert_eq(arb._drop_target_id, 2 if missing_hp > 0.0 else 1)
		assert_eq(arb.last_target_kind, "food" if missing_hp > 0.0 else "material")
		assert_eq(food[1], missing_hp)
		print("FRUIT value=%.1f chosen=%s id=%d" % [missing_hp, arb.last_target_kind, arb._drop_target_id])


func test_positive_tree_is_a_whole_map_target_with_no_attract_rim():
	for value in [4.0, 0.0, -4.0]:
		var tree = Collectible.reward(ORIGIN + Vector2(1500, 0), value, false, "tree", 1)
		var arb = Arbiter.new()
		_choose(arb, ORIGIN, [tree])
		assert_eq(arb.last_target_kind, "tree" if value > 0.0 else "none")
		assert_eq(tree[2], false)
	var near = Arbiter.new()
	_choose(near, ORIGIN, [Collectible.reward(ORIGIN + Vector2(30, 0), 4.0, false, "tree", 1)])
	assert_eq(near._drop_target_id, 1, "tree within the attract rim still must be reached")


func test_enemy_on_nearest_drop_is_not_selectable_even_beyond_threat_range():
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, [_material(Vector2(1500, 0), 1), _material(Vector2(-1600, 0), 2)],
		[[ORIGIN + Vector2(1500, 0), 25.0]])
	assert_eq(arb._drop_target_id, 2)
	assert_eq(arb.last_target_dist, 1600.0)
	# A giant body also forbids contact outside the nominal drop radius.
	var giant = Arbiter.new()
	_choose(giant, ORIGIN, [_material(Vector2(500, 0), 1)], [[ORIGIN + Vector2(700, 0), 220.0]])
	assert_eq(giant._drop_target_id, -1)


func test_target_and_path_threats_break_commitment_and_count_once():
	var drops = [_material(Vector2(600, 0), 1), _material(Vector2(-700, 0), 2)]
	for at in [Vector2(600, 100), Vector2(300, 100)]:
		var arb = Arbiter.new()
		_choose(arb, ORIGIN, drops)
		_choose(arb, ORIGIN, drops, [[ORIGIN + at, 25.0]])
		assert_eq(arb._drop_target_id, 2)
		assert_eq(arb.target_threat_drops, 1)
		assert_eq(arb.target_switches, 2)
		_choose(arb, ORIGIN, drops, [[ORIGIN + at, 25.0]])
		assert_eq(arb.target_threat_drops, 1, "rejected candidates are not counted as dropped commitments")


func test_path_risk_threshold_reselects_away_from_projectiles():
	var drops = [_material(Vector2(600, 0), 1), _material(Vector2(-700, 0), 2)]
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, drops)
	var threats = []
	for y in [40.0, 50.0, 60.0]:
		threats.append([ORIGIN + Vector2(220, y), Vector2.ZERO, 5.0, 10.0,
			Arbiter.KIND_PROJ, 0.0, 1.0, 1000.0])
	_choose(arb, ORIGIN, drops, [], threats)
	assert_eq(arb._drop_target_id, 2)
	assert_eq(arb.target_threat_drops, 1)


func test_smooth_danger_is_monotonic_and_close_hit_outprices_target_gain():
	var arb = Arbiter.new()
	var previous = -1.0
	for distance in [45.0, 70.0, 130.0, 200.0, 280.0, 420.0]:
		var factor = arb._smooth_danger(distance, 45.0)
		assert_true(factor >= previous and factor >= 0.0 and factor <= 1.0)
		previous = factor
		print("DANGER distance=%.1f factor=%.6f max_approach=%.6f" % [distance, factor, factor * Arbiter.TARGET_APPROACH_CAP])
	var threat = _contact(ORIGIN + Vector2(70, 0), Vector2(-180, 0), 40.0)
	var direction = _choose(arb, ORIGIN, [_material(Vector2(200, 0), 1)],
		[[threat[0], threat[2]]], [threat])
	assert_true(direction.x < 0.0)
	assert_true(104.0 > Arbiter.TARGET_APPROACH_CAP + Collectible.LEGENDARY_CRATE_VALUE)
	print("CLOSE_COST coefficient=104 max_approach=3 max_legendary_with_taken=5 dir=%s" % str(direction))


func test_looter_700_beats_material_300_and_is_a_whole_map_target():
	var unit = LootUnit.new()
	var loot = Collectible.loot(unit, 4.0)
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, [_material(Vector2(0, 300), 1), loot])
	assert_eq(arb._drop_target_id, unit.get_instance_id())
	assert_eq(arb.last_target_kind, "loot")
	assert_eq(loot[1], 8.0)
	unit.position = ORIGIN + Vector2(1500, 0)
	var far = Arbiter.new()
	var direction = _choose(far, ORIGIN, [Collectible.loot(unit, 4.0)])
	assert_eq(far.last_target_dist, 1500.0)
	assert_true(direction.x > 0.9, "selected loot outside 900 px still pulls")
	assert_eq(Collectible.loot(unit, 0.0), [], "Pacifist's disable gate is preserved")
	assert_eq(Collectible.loot(unit, -4.0)[1], 8.0, "any nonzero gate enables the named target value")
	print("LOOT_CROSSOVER material=300 value=3 loot=700 value=8 crossover=800 ratio=2.666667 far_dir=%s" % str(direction))


func test_looter_inside_pack_loses_to_clear_material():
	var unit = LootUnit.new()
	var loot = Collectible.loot(unit, 4.0)
	var material = _material(Vector2(0, -300), 1)
	var enemies = []
	for i in range(5):
		# Outside hard rejection; pooled route/near risk must demote the loot.
		enemies.append([unit.position + Vector2(0, 190 + i * 2), 25.0])
	var arb = Arbiter.new()
	var route = arb._target_route(ORIGIN, unit.position, enemies, [], 20.0)
	assert_eq(route[1], false, "fixture tests ranking, not only hard rejection")
	_choose(arb, ORIGIN, [loot, material], enemies)
	assert_eq(arb._drop_target_id, 1)
	print("LOOT_PACK loot_rank=%.6f material_rank=100 target=%s" % [700.0 / 8.0 * route[0], arb.last_target_kind])
	_choose(arb, ORIGIN, [loot, material], [[unit.position, 25.0]])
	assert_eq(arb._drop_target_id, 1, "an enemy on the looter also forbids its route")


func test_moving_looter_follows_live_position_without_material_flip_flopping():
	var unit = LootUnit.new()
	var arb = Arbiter.new()
	var pos = ORIGIN
	var held = 0
	var moved = 0
	var minimum = INF
	for tick in range(240):
		var time = tick / 60.0
		unit.position = ORIGIN + Vector2(700 + 30 * sin(time * 2.0), 100 * sin(time))
		var drops = [Collectible.loot(unit, 4.0), _material(Vector2(0, -300), 1)]
		var direction = _choose(arb, pos, drops)
		assert_eq(arb._drop_target_id, unit.get_instance_id(), "nearby material cannot steal a live commitment")
		assert_eq(arb._drop_target_pos, unit.position, "approach point tracks the live position")
		if direction == Vector2.ZERO:
			held += 1
		else:
			moved += 1
		pos += direction * SPEED / 60.0
		minimum = min(minimum, pos.distance_to(unit.position))
		if tick % 30 == 0 or tick == 239:
			print("LOOT_PATH tick=%d pos=%s loot=%s dir=%s distance=%.6f switches=%d" % [tick + 1, str(pos), str(unit.position), str(direction), pos.distance_to(unit.position), arb.target_switches])
	assert_eq(arb.target_switches, 1, "four seconds, one acquisition, no flip-flops")
	assert_true(held > 0 and moved > 0, "both follows and holds while the target wanders")
	assert_true(minimum > 40.0, "never body contact")
	assert_true(pos.distance_to(unit.position) <= 300.0, "ends in weapon range")
	print("LOOT_MOVING seconds=4 switches=%d held_ticks=%d moving_ticks=%d min_distance=%.6f final_distance=%.6f" % [arb.target_switches, held, moved, minimum, pos.distance_to(unit.position)])


func test_looter_holds_standoff_without_contact_or_pickup_payout():
	for weapon_range in [100.0, 300.0, 1000.0]:
		var unit = LootUnit.new()
		var arb = Arbiter.new()
		var pos = ORIGIN
		var held = 0
		var minimum = INF
		for tick in range(180):
			var direction = _choose(arb, pos, [Collectible.loot(unit, 4.0)], [], [], weapon_range)
			pos += direction * SPEED / 60.0
			minimum = min(minimum, pos.distance_to(unit.position))
			if tick >= 150 and direction == Vector2.ZERO:
				held += 1
		assert_eq(held, 30, "holds still for the final half-second")
		assert_eq(arb._drop_target_id, unit.get_instance_id(), "in-range loot remains held, not collected")
		assert_true(minimum > 40.0, "body remains clear")
		assert_true(pos.distance_to(unit.position) <= arb._loot_standoff)
		assert_true(pos.distance_to(unit.position) >= arb._loot_standoff - SPEED / 60.0 - 0.01)
		assert_true(pos.distance_to(unit.position) < weapon_range)
		print("LOOT_HOLD weapon=%.1f standoff=%.1f distance=%.6f held_ticks=%d" % [weapon_range, arb._loot_standoff, pos.distance_to(unit.position), held])
	# pickup_taken cannot turn a chase into a body-contact reward.
	var unit = LootUnit.new()
	var standard = Arbiter.new()
	var huge_taken = Arbiter.new()
	huge_taken.pickup_taken = 1000.0
	_choose(standard, ORIGIN, [Collectible.loot(unit, 4.0)])
	_choose(huge_taken, ORIGIN, [Collectible.loot(unit, 4.0)])
	assert_eq(standard.last_scores, huge_taken.last_scores)


func test_looter_death_pending_cull_and_freed_unit_release_target():
	for outcome in ["dead", "pending", "freed", "removed"]:
		var unit = LootUnit.new()
		var arb = Arbiter.new()
		_choose(arb, ORIGIN, [Collectible.loot(unit, 4.0)])
		assert_eq(arb.last_target_kind, "loot")
		if outcome == "dead":
			unit.dead = true
		elif outcome == "pending":
			unit._pending_die = true
		elif outcome == "freed":
			var weak = weakref(unit)
			unit = null    # Reference frees itself when the last strong reference goes away
			assert_eq(weak.get_ref(), null)
		var loot = [] if outcome == "removed" else Collectible.loot(unit, 4.0)
		assert_eq(loot, [])
		_choose(arb, ORIGIN, [_material(Vector2(0, 300), 1)])
		assert_eq(arb._drop_target_id, 1, "gone loot yields to the material: " + outcome)
		assert_eq(arb.target_switches, 2)
		assert_eq(arb.target_threat_drops, 0)


func test_loot_hold_yields_to_danger_and_steps_out_of_body_overlap():
	var unit = LootUnit.new()
	unit.position = ORIGIN + Vector2(200, 0)
	var quiet = Arbiter.new()
	assert_eq(_choose(quiet, ORIGIN, [Collectible.loot(unit, 4.0)]), Vector2.ZERO)
	# Holding range is an opportunity term; a live bullet still forces a dodge.
	var threat = [ORIGIN + Vector2(70, 0), Vector2(-180, 0), 25.0, 40.0,
		Arbiter.KIND_PROJ, 0.0, 1.0, 1000.0]
	var danger = Arbiter.new()
	var direction = _choose(danger, ORIGIN, [Collectible.loot(unit, 4.0)], [], [threat])
	assert_true(direction.x < 0.0, "holding never overrides a close bullet")
	unit.position = ORIGIN + Vector2(30, 0)
	var overlapping = Arbiter.new()
	direction = _choose(overlapping, ORIGIN, [Collectible.loot(unit, 4.0)])
	assert_true(direction.x < 0.0, "an overlapping loot body does not trap the bot in a hold")


func test_loot_overlap_escape_scores_beat_through_body_independent_of_candidate_order():
	for toward in [Vector2.RIGHT, Vector2.DOWN, Vector2.LEFT, Vector2.UP]:
		var unit = LootUnit.new()
		unit.position = ORIGIN + toward * 30.0
		var rewards = [Collectible.loot(unit, 4.0)]
		var arb = Arbiter.new()
		var direction = _choose(arb, ORIGIN, rewards)
		assert_true(direction.dot(toward) < 0.0, "escapes with the looter on every side")
		# Give every comparison the same continuity state. Strictly cheaper
		# escape/tangent scores cannot tie with through-body by enumeration order.
		arb.last_dir = Vector2.ZERO
		var headings = [toward, -toward, toward.tangent(), -toward.tangent()]
		var costs = []
		for heading in headings:
			costs.append(arb._cost(heading, ORIGIN, SPEED, 20.0, FAR,
				rewards, [], [], 300.0, false, 100.0))
		for i in range(1, costs.size()):
			assert_true(costs[i] < costs[0], "away and both tangents strictly beat through-body")
		for i in range(headings.size() - 1, -1, -1):
			assert_eq(arb._cost(headings[i], ORIGIN, SPEED, 20.0, FAR,
				rewards, [], [], 300.0, false, 100.0), costs[i], "reverse evaluation order preserves scores")
		# Even existing inward momentum must not make through-body win.
		var inward = Arbiter.new()
		inward.last_dir = toward
		var inward_direction = _choose(inward, ORIGIN, rewards)
		assert_true(inward_direction.dot(toward) <= 0.0, "escapes or sidesteps despite inward momentum")
		print("LOOT_OVERLAP toward=%s chosen=%s inward_chosen=%s through=%.6f away=%.6f tangent_a=%.6f tangent_b=%.6f" % [str(toward), str(direction), str(inward_direction), costs[0], costs[1], costs[2], costs[3]])


func test_held_looter_overlap_steps_out_and_resumes_safe_standoff():
	var unit = LootUnit.new()
	unit.position = ORIGIN + Vector2(200, 0)
	var arb = Arbiter.new()
	var pos = ORIGIN
	assert_eq(_choose(arb, pos, [Collectible.loot(unit, 4.0)]), Vector2.ZERO)
	assert_eq(arb._drop_target_id, unit.get_instance_id(), "looter is already the held target")
	unit.position = pos + Vector2(30, 0)    # the held looter wanders into the player
	var cleared_tick = -1
	var held = 0
	for tick in range(120):
		var start = pos
		var distance = start.distance_to(unit.position)
		var direction = _choose(arb, pos, [Collectible.loot(unit, 4.0)])
		pos += direction * SPEED / 60.0
		assert_eq(arb._drop_target_id, unit.get_instance_id(), "escape keeps the living target")
		if distance <= 40.0:
			assert_true(direction.dot(start - unit.position) >= 0.0, "never starts by penetrating farther")
			assert_true(pos.distance_to(unit.position) > distance, "takes a step out instead of holding")
		else:
			var closest = Geometry.get_closest_point_to_segment_2d(unit.position, start, pos)
			assert_true(closest.distance_to(unit.position) > 40.0, "never reenters contact after escape")
		if cleared_tick == -1 and pos.distance_to(unit.position) > 40.0:
			cleared_tick = tick + 1
		if tick >= 90 and direction == Vector2.ZERO:
			held += 1
		if tick < 6 or tick == 119:
			print("LOOT_OVERLAP_HOLD_PATH tick=%d pos=%s dir=%s distance=%.6f" % [tick + 1, str(pos), str(direction), pos.distance_to(unit.position)])
	assert_true(cleared_tick > 0, "escapes the initial overlap")
	assert_eq(held, 30, "resumes holding inside weapon standoff for the final half-second")
	assert_true(pos.distance_to(unit.position) <= arb._loot_standoff)
	assert_true(pos.distance_to(unit.position) > 40.0)
	assert_eq(arb.target_switches, 1, "step-out never replaces the held target")
	assert_eq(arb.target_threat_drops, 0)
	print("LOOT_OVERLAP_HOLD seconds=2 clear_tick=%d clear_time=%.6f final_distance=%.6f standoff=%.1f held_ticks=%d switches=%d" % [cleared_tick, cleared_tick / 60.0, pos.distance_to(unit.position), arb._loot_standoff, held, arb.target_switches])


func test_linear_legacy_loot_reward_ignores_target_metadata():
	var unit = LootUnit.new()
	var legacy = Arbiter.new()
	var linear = Arbiter.new()
	var rewards = [[unit.position, 4.0]]
	legacy.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0,
		{"pickup_radius": RIM})
	linear.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0,
		{"drop_pull": "linear", "pickup_radius": RIM,
		"target_collectibles": [Collectible.loot(unit, 4.0)]})
	assert_eq(linear.last_dirs, legacy.last_dirs)
	assert_eq(linear.last_scores, legacy.last_scores, "legacy two-field loot scoring is unchanged")
	assert_eq(linear.last_target_kind, "none")


func test_walking_enemy_reselects_or_keeps_live_route_clear_and_avoids_contact_for_two_seconds():
	var arb = Arbiter.new()
	var pos = ORIGIN
	var enemy = ORIGIN + Vector2(300, -200)
	var velocity = Vector2(0, 200)
	var drops = [_material(Vector2(600, 0), 1), _material(Vector2(-700, 0), 2)]
	_choose(arb, pos, drops)
	assert_eq(arb._drop_target_id, 1)
	var minimum = INF
	var route_minimum = INF
	var switched = false
	for tick in range(120):
		var threat = _contact(enemy, velocity)
		var direction = _choose(arb, pos, drops, [[enemy, 25.0]], [threat])
		assert_true(arb._drop_target_id != -1, "clear-route branch requires a live target every tick")
		var route = Geometry.get_closest_point_to_segment_2d(enemy, pos, arb._drop_target_pos)
		route_minimum = min(route_minimum, route.distance_to(enemy))
		var old = pos
		pos += direction * SPEED / 60.0
		var relative = Geometry.get_closest_point_to_segment_2d(Vector2.ZERO,
			old - enemy, pos - (enemy + velocity / 60.0))
		minimum = min(minimum, relative.length())
		enemy += velocity / 60.0
		route = Geometry.get_closest_point_to_segment_2d(enemy, pos, arb._drop_target_pos)
		route_minimum = min(route_minimum, route.distance_to(enemy))
		if arb.target_threat_drops > 0 and arb._drop_target_id == 2:
			switched = true
		if tick % 10 == 0 or tick == 119:
			print("WALK_PATH tick=%d pos=%s enemy=%s dir=%s target=%d drops=%d minimum=%.6f" % [tick + 1, str(pos), str(enemy), str(direction), arb._drop_target_id, arb.target_threat_drops, minimum])
	assert_true(switched or route_minimum >= Arbiter.TARGET_DROP_PATH_RADIUS,
		"drop and reselect away from the enemy, or keep the live route clear every tick")
	assert_true(minimum > 45.0, "continuous relative move never enters combined contact radius")
	var branch = "dropped_and_reselected" if switched else "live_route_clear"
	print("WALK_SUMMARY branch=%s seconds=2 min_contact_distance=%.6f contact_radius=45 min_route_clearance=%.6f path_radius=%.1f target=%d threat_drops=%d pos=%s" % [branch, minimum, route_minimum, Arbiter.TARGET_DROP_PATH_RADIUS, arb._drop_target_id, arb.target_threat_drops, str(pos)])


func test_enemy_spawns_on_live_route_forces_drop_and_reselection_away():
	var arb = Arbiter.new()
	var pos = ORIGIN
	var drops = [_material(Vector2(600, 0), 1), _material(Vector2(-700, 0), 2)]
	_choose(arb, pos, drops)
	assert_eq(arb._drop_target_id, 1)
	# Spawn after commitment, on the live route 150 px ahead. The next
	# decision must invalidate it before movement can curve the route away.
	var enemy = pos + Vector2(150, 0)
	var blocked_route = Geometry.get_closest_point_to_segment_2d(enemy, pos, arb._drop_target_pos)
	var initial_clearance = blocked_route.distance_to(enemy)
	assert_true(initial_clearance < Arbiter.TARGET_DROP_PATH_RADIUS)
	var minimum = INF
	for tick in range(120):
		var direction = _choose(arb, pos, drops, [[enemy, 25.0]], [_contact(enemy, Vector2.ZERO)])
		if tick == 0:
			assert_true(arb.target_threat_drops >= 1, "spawning in the band drops the commitment immediately")
			assert_eq(arb._drop_target_id, 2, "reselects the material on the opposite side")
			assert_true((arb._drop_target_pos - pos).dot(enemy - pos) < 0.0,
				"reselected target leads away from the enemy")
			assert_true(direction.dot(enemy - pos) < 0.0, "first move increases separation")
		var old = pos
		pos += direction * SPEED / 60.0
		var closest = Geometry.get_closest_point_to_segment_2d(enemy, old, pos)
		minimum = min(minimum, closest.distance_to(enemy))
		if tick % 10 == 0 or tick == 119:
			print("SPAWN_PATH tick=%d pos=%s enemy=%s dir=%s target=%d drops=%d minimum=%.6f" % [tick + 1, str(pos), str(enemy), str(direction), arb._drop_target_id, arb.target_threat_drops, minimum])
	assert_true(arb.target_threat_drops >= 1)
	assert_eq(arb._drop_target_id, 2)
	assert_true(minimum > 45.0, "spawn fixture never enters combined contact radius")
	print("SPAWN_SUMMARY seconds=2 spawn_ahead=150 initial_route_clearance=%.6f path_radius=%.1f min_contact_distance=%.6f contact_radius=45 target=%d threat_drops=%d switches=%d pos=%s" % [initial_clearance, Arbiter.TARGET_DROP_PATH_RADIUS, minimum, arb._drop_target_id, arb.target_threat_drops, arb.target_switches, str(pos)])


func test_pack_beyond_target_does_not_lure_bot_within_200_px():
	var arb = Arbiter.new()
	var pos = ORIGIN
	var drops = [_material(Vector2(300, 0), 1)]
	var enemies = []
	var threats = []
	for i in range(5):
		# Pack is 400-500 px BEYOND the target, initially quiet at player.
		var at = ORIGIN + Vector2(700 + i * 25, (i - 2) * 20)
		enemies.append([at, 25.0])
		threats.append(_contact(at, Vector2.ZERO))
	var end_distance = INF
	for tick in range(240):
		var direction = _choose(arb, pos, drops, enemies, threats)
		var start = pos
		pos += direction * SPEED / 60.0
		if not drops.empty() and Geometry.get_closest_point_to_segment_2d(drops[0][0], start, pos).distance_to(drops[0][0]) <= RIM:
			drops = []
		end_distance = INF
		for e in enemies:
			end_distance = min(end_distance, pos.distance_to(e[0]))
		if tick % 30 == 0 or tick == 239:
			print("PACK_PATH tick=%d pos=%s dir=%s pack_distance=%.6f remaining=%d" % [tick + 1, str(pos), str(direction), end_distance, drops.size()])
	assert_true(end_distance >= 200.0, "does not finish inside 200 px of the pack")
	print("PACK_SUMMARY seconds=4 pos=%s nearest=%.6f" % [str(pos), end_distance])
