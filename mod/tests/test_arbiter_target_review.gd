extends "res://mod/tests/test_base.gd"

const Arbiter = preload("res://mod/Ellie-BrotatoBot/steering/arbiter.gd")
const Collectible = preload("res://mod/Ellie-BrotatoBot/steering/collectible.gd")
const ORIGIN = Vector2(1500, 1500)
const FAR = Vector2(4000, 4000)


class Weapon extends Reference:
	var stats = {"damage": 5.0, "cooldown": 30.0, "max_range": 300.0}


class ExhaustiveArbiter extends "res://mod/Ellie-BrotatoBot/steering/arbiter.gd":
	func _update_drop_target(p0: Vector2, rewards: Array, enemies: Array,
			threats: Array, body_radius: float, _prune: bool = true):
		._update_drop_target(p0, rewards, enemies, threats, body_radius, false)


func _material(offset: Vector2, id: int, value: float = 3.0) -> Array:
	return Collectible.reward(ORIGIN + offset, value, true, "floor_drop", id)


func _loot(offset: Vector2, id: int) -> Array:
	var r = Collectible.reward(ORIGIN + offset, 8.0, false, "loot", id)
	r.append(20.0)
	return r


func _choose(arb, pos: Vector2, drops: Array, threats: Array = [], enemies: Array = [],
		can_damage: bool = true, weapon_range: float = 300.0) -> Vector2:
	return arb.choose(pos, 300.0, 20.0, FAR, threats, drops, [], [], weapon_range,
		false, 100.0, 1.0, {"drop_pull": "target", "pickup_radius": 60.0,
		"target_collectibles": drops, "target_enemies": enemies, "loot_can_damage": can_damage})


func _threat(offset: Vector2, velocity: Vector2, kind: int, damage: float = 10.0) -> Array:
	return [ORIGIN + offset, velocity, 25.0, damage, kind, 0.0, 1.0, 1000.0]


func test_weaponless_and_nondamaging_builds_do_not_chase_loot_and_release_it():
	var weapon = Weapon.new()
	assert_eq(Collectible.can_damage([]), false, "Bull / weapon_slot 0")
	assert_eq(Collectible.can_damage([null]), false)
	assert_eq(Collectible.can_damage([weapon]), true)
	for field in ["damage", "cooldown", "max_range"]:
		var old = weapon.stats[field]
		weapon.stats[field] = 0.0
		assert_eq(Collectible.can_damage([weapon]), false, "cannot damage with " + field + " zero")
		weapon.stats[field] = old
	var loot = _loot(Vector2(200, 0), 1)
	var material = _material(Vector2(0, 600), 2)
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, [loot, material])
	assert_eq(arb.last_target_kind, "loot")
	var direction = _choose(arb, ORIGIN, [loot, material], [], [], false)
	assert_eq(arb._drop_target_id, 2, "losing damage capability releases a held looter")
	assert_true(direction.y > 0.9)
	var empty = Arbiter.new()
	_choose(empty, ORIGIN, [loot], [], [], false)
	assert_eq(empty._drop_target_id, -1)
	var no_range = Arbiter.new()
	_choose(no_range, ORIGIN, [loot], [], [], true, 0.0)
	assert_eq(no_range._drop_target_id, -1)


func test_loot_and_tree_holds_time_out_and_same_unit_observes_cooldown():
	for kind in ["loot", "tree"]:
		for step in [1, 2]:
			var arb = Arbiter.new()
			arb.tick_step = step
			var shoot = _loot(Vector2(200, 0), 1) if kind == "loot" else \
				Collectible.reward(ORIGIN + Vector2(200, 0), 4.0, false, "tree", 1)
			var drops = [shoot, _material(Vector2(0, 600), 2)]
			assert_eq(_choose(arb, ORIGIN, drops), Vector2.ZERO, "holds inside weapon standoff")
			assert_eq(arb._drop_target_id, 1)
			var ticks = 0
			while arb._drop_target_id == 1 and ticks < 260:
				_choose(arb, ORIGIN, drops)
				ticks += step
			assert_true(ticks >= 240 and ticks <= 242, "four physics seconds of hold")
			assert_eq(arb._drop_target_id, 2, "failed hold releases to material")
			for _i in range(100):
				_choose(arb, ORIGIN, drops)
				assert_eq(arb._drop_target_id, 2, "same unit stays on cooldown")
			# Remove the alternative and advance past the remaining cooldown.
			for _i in range(250):
				_choose(arb, ORIGIN, [shoot])
				if arb._drop_target_id == 1:
					break
			assert_eq(arb._drop_target_id, 1, "eligible again after the bounded cooldown")
			assert_true(arb._shoot_hold < 0.1, "reacquisition starts a fresh hold")
			print("SHOOT_TIMEOUT kind=%s tick_step=%d hold_ticks=%d hold_seconds=%.6f cooldown=%.1f" % [kind, step, ticks, ticks / 60.0, Arbiter.SHOOT_TARGET_COOLDOWN])


func test_tree_standoff_stops_short_then_yields_to_other_targets_without_a_kill():
	var arb = Arbiter.new()
	var pos = ORIGIN
	var tree = Collectible.reward(ORIGIN + Vector2(500, 0), 4.0, false, "tree", 1)
	var material = _material(Vector2(-600, 0), 2)
	var minimum = INF
	var holds = 0
	var yielded = false
	for tick in range(360):
		var direction = _choose(arb, pos, [tree, material])
		pos += direction * 5.0
		minimum = min(minimum, pos.distance_to(tree[0]))
		if arb._drop_target_id == 1 and direction == Vector2.ZERO:
			holds += 1
		if arb._drop_target_id == 2:
			yielded = true
			assert_true(direction.x < 0.0, "walks away to the material after timeout")
			break
	assert_true(holds >= 239, "gives weapons four seconds to fell it")
	assert_true(minimum >= 235.0 and minimum <= 240.0, "holds at weapon standoff, away from centre")
	assert_true(yielded, "living tree cannot block every other target")
	print("TREE_PATH min_distance=%.6f hold_ticks=%d yielded=%s final=%s" % [minimum, holds, str(yielded), str(pos)])


func test_close_receding_and_passing_threats_keep_target_pull_and_fast_closer_dodges():
	var material = _material(Vector2(600, 0), 1, 0.8)
	var fixtures = [
		_threat(Vector2(-150, 0), Vector2(-20, 0), Arbiter.KIND_CONTACT),
		_threat(Vector2(-100, 150), Vector2(200, 0), Arbiter.KIND_PROJ),
		_threat(Vector2(-150, 0), Vector2(-200, 0), Arbiter.KIND_PROJ)]
	for threat in fixtures:
		var arb = Arbiter.new()
		var enemies = [[threat[0], threat[2]]] if threat[4] == Arbiter.KIND_CONTACT else []
		var direction = _choose(arb, ORIGIN, [material], [threat], enemies)
		assert_eq(arb._drop_target_id, 1, "route remains clear")
		assert_eq(arb._target_danger, 1.0, "receding or missing paths do not reduce pull")
		assert_true(direction.x > 0.8, "stationary player still starts walking to target (a passing bullet may bend the heading up to ~35 deg)")
		print("CLOSING_RULE kind=%d velocity=%s dir=%s danger=%.6f" % [threat[4], str(threat[1]), str(direction), arb._target_danger])
	# The enemy is behind the player, leaving the target route unblocked. It
	# closes faster than we walk: the existing contact costs must force a sidestep.
	var threat = _threat(Vector2(-150, 0), Vector2(500, 0), Arbiter.KIND_CONTACT, 40.0)
	var arb = Arbiter.new()
	var direction = _choose(arb, ORIGIN, [material], [threat], [[threat[0], threat[2]]])
	assert_eq(arb._drop_target_id, 1, "closing danger does not switch collection off")
	assert_true(arb._target_danger < 1.0)
	assert_true(abs(direction.y) > 0.5, "fast closer forces a lateral dodge")
	assert_true(arb._target_approach(0.8, 1.0) > arb.w_hyst, "danger floor still beats standing")
	print("FAST_CLOSER dir=%s danger=%.6f approach_floor=%.6f" % [str(direction), arb._target_danger, arb._target_approach(0.8, 1.0)])


func _random_point(rng, radius: float) -> Vector2:
	return ORIGIN + Vector2(rng.randf_range(-radius, radius), rng.randf_range(-radius, radius))


func _fixture(rng, count: int, enemy_count: int, projectile_count: int) -> Array:
	var rewards = []
	for i in range(count):
		var kind = ["floor_drop", "crate", "food", "tree", "loot"][i % 5]
		var value = rng.randf_range(0.1, 12.0)
		if kind == "crate":
			value = Collectible.CRATE_VALUE if i % 2 else Collectible.LEGENDARY_CRATE_VALUE
		var r = Collectible.reward(_random_point(rng, 1800), value,
			kind in ["floor_drop", "crate", "food"], kind, i + 1)
		if kind == "loot":
			r.append(20.0)
		rewards.append(r)
	var enemies = []
	for _i in range(enemy_count):
		enemies.append([_random_point(rng, 2200), rng.randf_range(10.0, 250.0)])
	var threats = []
	for _i in range(projectile_count):
		threats.append([_random_point(rng, 2200), Vector2(rng.randf_range(-500, 500), rng.randf_range(-500, 500)),
			rng.randf_range(5, 60), rng.randf_range(1, 40), Arbiter.KIND_PROJ,
			rng.randf_range(0, 0.9), 1.0, rng.randf_range(-0.1, 2.0)])
	return [rewards, enemies, threats]


func test_exact_pruning_matches_exhaustive_selection_on_600_seeded_mixed_fixtures():
	var rng = RandomNumberGenerator.new()
	rng.seed = 20261024
	for case in range(600):
		var f = _fixture(rng, 25, case % 31, case % 21)
		var pruned = Arbiter.new()
		var full = ExhaustiveArbiter.new()
		var current_id = case % 26   # includes no current and every collectible kind
		for arb in [pruned, full]:
			arb._drop_target_id = current_id
			arb._loot_standoff = 240.0
			arb._pickup_radius = 60.0
			arb._target_on = true
			arb._update_drop_target(ORIGIN, f[0], f[1], f[2], 20.0)
		assert_eq(pruned._drop_target_id, full._drop_target_id, "same id at seed case %d" % case)
		assert_eq(pruned.last_target_kind, full.last_target_kind)
		assert_eq(pruned.target_threat_drops, full.target_threat_drops, "current always checked")
		# Change the route after commitment; both must retain or release identically.
		f[1].append([pruned._drop_target_pos, 25.0])
		for arb in [pruned, full]:
			arb._update_drop_target(ORIGIN, f[0], f[1], f[2], 20.0)
		assert_eq(pruned._drop_target_id, full._drop_target_id)
		assert_eq(pruned.target_threat_drops, full.target_threat_drops)
	print("PRUNE_EQUIVALENCE seed=20261024 cases=600 decisions=1200 kinds=material,crate,food,tree,loot current=all")


func test_headless_selection_timing_60_collectibles_100_enemies_50_projectiles():
	var rng = RandomNumberGenerator.new()
	rng.seed = 50241026
	var fixtures = []
	for _i in range(30):
		fixtures.append(_fixture(rng, 60, 100, 50))
	var timings = []
	for prune in [false, true]:
		var arb = Arbiter.new()
		arb._target_on = true
		arb._pickup_radius = 60.0
		arb._loot_standoff = 240.0
		var started = OS.get_ticks_usec()
		for f in fixtures:
			arb._update_drop_target(ORIGIN, f[0], f[1], f[2], 20.0, prune)
		timings.append(float(OS.get_ticks_usec() - started) / fixtures.size())
	assert_true(timings[0] > 0.0 and timings[1] > 0.0, "timing is evidence, not a flaky speed assertion")
	print("PRUNE_TIMING collectibles=60 enemies=100 projectiles=50 decisions=30 before_mean_us=%.1f after_mean_us=%.1f ratio=%.3f" % [timings[0], timings[1], timings[0] / timings[1]])
