extends "res://mod/tests/test_base.gd"

const Arbiter = preload("res://mod/Ellie-BrotatoBot/steering/arbiter.gd")
const Collectible = preload("res://mod/Ellie-BrotatoBot/steering/collectible.gd")
const FloorDrop = preload("res://mod/Ellie-BrotatoBot/steering/floor_drop.gd")
const ORIGIN = Vector2(1500, 1500)
const FAR = Vector2(4000, 4000)
const SPEED = 300.0
const RIM = 60.0


func _material(offset: Vector2, id: int, value: float = 3.0) -> Array:
	return FloorDrop.reward(ORIGIN + offset, value, 1.0, id)


func _choose(arb, pos: Vector2, drops: Array, enemies: Array = [], threats: Array = []) -> Vector2:
	var local = []
	for r in drops:
		if pos.distance_to(r[0]) < 900.0:
			local.append(r)
	return arb.choose(pos, SPEED, 20.0, FAR, threats, local, [], [], 300.0, false, 100.0, 1.0,
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


func test_crates_rank_above_material_and_legendary_above_normal():
	var material = _material(Vector2(300, 0), 1)
	var crate = Collectible.consumable(ORIGIN + Vector2(0, 400), "consumable_item_box", 0.0, 2)
	var legendary = Collectible.consumable(crate[0], "consumable_legendary_item_box", 0.0, 3)
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, [material, crate])
	assert_eq(arb._drop_target_id, 2, "crate at 400 beats material at 300")
	assert_eq(arb.last_target_kind, "crate")
	_choose(Arbiter.new(), ORIGIN, [material, legendary])
	var ranked = Arbiter.new()
	_choose(ranked, ORIGIN, [crate, legendary])
	assert_eq(ranked._drop_target_id, 3)
	crate[0] = ORIGIN + Vector2(0, 600)
	var tied = Arbiter.new()
	_choose(tied, ORIGIN, [material, crate])
	assert_eq(tied._drop_target_id, 1, "600/6 == 300/3; earlier material wins exact tie")
	crate[0] = ORIGIN + Vector2(0, 599)
	var closer = Arbiter.new()
	_choose(closer, ORIGIN, [material, crate])
	assert_eq(closer._drop_target_id, 2, "crate wins below crossover")
	print("CRATE_CROSSOVER material=300 value=3 normal_value=%.1f crossover=600 legendary_value=%.1f crossover=1200" % [Collectible.CRATE_VALUE, Collectible.LEGENDARY_CRATE_VALUE])


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
	print("CLOSE_COST coefficient=104 max_approach=3 max_legendary_with_taken=15 dir=%s" % str(direction))


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
