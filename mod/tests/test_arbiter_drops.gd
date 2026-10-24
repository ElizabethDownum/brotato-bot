extends "res://mod/tests/test_base.gd"

const Arbiter = preload("res://mod/Ellie-BrotatoBot/steering/arbiter.gd")
const Steering = preload("res://mod/Ellie-BrotatoBot/core/steering_overrides.gd")
const FloorDrop = preload("res://mod/Ellie-BrotatoBot/steering/floor_drop.gd")
const ORIGIN = Vector2(1500, 1500)
const FAR = Vector2(3000, 3000)
const SPEED = 300.0
const PICKUP_RIM = 60.0
# The 15-degree candidate grid can require a final-approach sidestep before
# collection. Allow a reversal only within this margin beyond the target rim.
const FINAL_APPROACH_REVERSAL_MARGIN = 24.0


# Twelve unevenly spaced pairs, unequal radii and face values. The live
# world view prices each gold entity equally, independent of its face value.
func _drops() -> Array:
	var drops = []
	var angles = [0, 11, 28, 47, 59, 76, 94, 108, 127, 143, 159, 172]
	for i in range(angles.size()):
		var offset = Vector2.RIGHT.rotated(deg2rad(angles[i])) * (150.0 + (i * 37) % 151)
		for sign_ in [-1, 1]:
			drops.append({"id": drops.size() + 1, "position": ORIGIN + offset * sign_, "value": 1 + i % 4})
	return drops


func _rewards(drops: Array) -> Array:
	var rewards = []
	for drop in drops:
		# Well Rounded: gold .8 * quiet draw 1.5 * sweep 2.5.
		rewards.append(FloorDrop.reward(drop.position, 0.8 * 2.5, 1.5, drop.id))
	return rewards


func _choose(arb, pos, drops, profile = {}, threats = []) -> Vector2:
	var resolved = Steering.resolve({"gold": 0.8}, {"sweep": 2.5})
	resolved.pickup_radius = PICKUP_RIM
	resolved.drop_quiet = threats.empty()
	for key in profile:
		resolved[key] = profile[key]
	resolved.target_collectibles = _rewards(drops)
	resolved.target_enemies = []
	for t in threats:
		if t[4] in [Arbiter.KIND_CONTACT, Arbiter.KIND_DASH]:
			resolved.target_enemies.append([t[0], t[2]])
	var in_range = []
	for drop in drops:
		if pos.distance_to(drop.position) < 900.0:
			in_range.append(drop)
	return arb.choose(pos, SPEED, 20.0, FAR, threats, _rewards(in_range), [], [],
		300.0, false, 100.0, 1.0, resolved)


func test_ring_baseline_stands_and_reports_all_candidates():
	var arb = Arbiter.new()
	var choice = _choose(arb, ORIGIN, _drops())
	assert_eq(choice, Vector2.ZERO, "linear ring reproduces the stand")
	for i in range(arb.last_scores.size()):
		print("RING_BASELINE candidate=%d dir=%s total=%.6f" % [
			i, str(arb.last_dirs[i]), arb.last_scores[i]])


func test_asymmetric_baseline_reports_choice():
	var drops = _drops()
	for i in range(8):
		drops.append({"id": drops.size() + 1, "position": ORIGIN + Vector2(170 + i * 12, i * 7), "value": 1 + i % 3})
	var arb = Arbiter.new()
	var choice = _choose(arb, ORIGIN, drops)
	print("ASYMMETRIC_BASELINE dir=%s total=%.6f" % [str(choice), arb.last_scores[arb.last_best_index]])
	assert_true(choice.x > 0.0, "asymmetric floor moves toward the extra drops")
	var target = Arbiter.new()
	choice = _choose(target, ORIGIN, drops, {"drop_pull": "target"})
	print("ASYMMETRIC_TARGET dir=%s target=%d pos=%s dtg=%.6f" % [
		str(choice), target._drop_target_id, str(target._drop_target_pos), target.last_target_dist])
	assert_eq(target._drop_target_id, 1, "nearest 150 px drop wins, tied with its opposite")


func test_close_body_and_projectile_override_floor_pull():
	for mode in ["linear", "target"]:
		for kind in [Arbiter.KIND_CONTACT, Arbiter.KIND_PROJ, Arbiter.KIND_DASH]:
			var threat = [ORIGIN + Vector2(70, 0), Vector2(-180, 0), 25.0, 40.0,
				kind, 0.0, 1.0, 1000.0]
			var arb = Arbiter.new()
			var choice = _choose(arb, ORIGIN, _drops(), {"drop_pull": mode}, [threat])
			print("DODGE mode=%s kind=%d dir=%s dtg=%.6f" % [mode, kind, str(choice), arb.last_target_dist])
			assert_true(choice.x < 0.0, "%s dodge close threat kind %d" % [mode, kind])


func test_target_moves_and_explicit_linear_matches_default_scores():
	var baseline = Arbiter.new()
	_choose(baseline, ORIGIN, _drops())
	var linear = Arbiter.new()
	assert_eq(_choose(linear, ORIGIN, _drops(), {"drop_pull": "linear"}), Vector2.ZERO)
	assert_eq(linear.last_scores, baseline.last_scores, "linear preserves every candidate total")
	var target = Arbiter.new()
	var choice = _choose(target, ORIGIN, _drops(), {"drop_pull": "target"})
	assert_true(choice != Vector2.ZERO, "target escapes the ring")
	print("RING_TARGET dir=%s total=%.6f" % [str(choice), target.last_scores[target.last_best_index]])
	print("RING_TARGET_SCORES dirs=%s totals=%s" % [str(target.last_dirs), str(target.last_scores)])


func test_linear_floor_tuple_scores_equal_legacy_ring_scores():
	var marked = Arbiter.new()
	_choose(marked, ORIGIN, _drops(), {"drop_pull": "linear"})
	var legacy = Arbiter.new()
	var rewards = []
	for r in _rewards(_drops()):
		rewards.append([r[0], r[1]])
	legacy.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [],
		300.0, false, 100.0, 1.0, {"drop_pull": "linear", "pickup_radius": PICKUP_RIM})
	assert_eq(marked.last_dirs, legacy.last_dirs)
	assert_eq(marked.last_scores, legacy.last_scores, "six-field floor tuples preserve legacy two-field ring totals")


func test_non_quiet_target_keeps_committed_approach_without_linear_fallback():
	var rewards = []
	for drop in _drops():
		# A contact-time WorldView tick disables draw/sweep: gold .8, draw 1.
		rewards.append(FloorDrop.reward(drop.position, 0.8, 1.0, drop.id))
	var target = Arbiter.new()
	var linear = Arbiter.new()
	# Closing the old quiet gate alone must neither clear nor change scoring.
	_choose(target, ORIGIN, _drops(), {"drop_pull": "target"})
	linear.last_dir = target.last_dir
	for arb in [target, linear]:
		var mode = "target" if arb == target else "linear"
		arb.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [],
			300.0, false, 100.0, 1.0,
			{"drop_pull": mode, "drop_quiet": false, "pickup_radius": PICKUP_RIM})
	assert_eq(target._drop_target_id, 1)
	assert_eq(target.last_target_kind, "material")
	assert_true(target.last_scores != linear.last_scores, "closed quiet gate still uses target scoring")
	assert_true(target._target_on)


func test_quiet_target_scores_only_committed_approach():
	var rewards = [FloorDrop.reward(ORIGIN + Vector2(400, 0), 3.0, 1.0, 1),
		FloorDrop.reward(ORIGIN + Vector2(-420, 0), 3.0, 1.0, 2)]
	var target = Arbiter.new()
	var solo = Arbiter.new()
	var linear = Arbiter.new()
	var profile = {"drop_pull": "target", "drop_quiet": true, "pickup_radius": PICKUP_RIM}
	target.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0, profile)
	solo.choose(ORIGIN, SPEED, 20.0, FAR, [], [rewards[0]], [], [], 300.0, false, 100.0, 1.0, profile)
	profile.drop_pull = "linear"
	linear.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0, profile)
	assert_eq(target._drop_target_id, 1)
	assert_eq(target.last_target_dist, 400.0)
	assert_eq(target.last_scores, solo.last_scores, "quiet non-target outside reach contributes no approach")
	assert_true(target.last_scores != linear.last_scores, "quiet tick keeps target scoring")


func test_unreachable_non_target_drops_preserve_ring_scores():
	var ring = Arbiter.new()
	_choose(ring, ORIGIN, _drops(), {"drop_pull": "target"})
	var drops = _drops()
	# These non-targets cannot be crossed within the 240 px projected move
	# plus rim. Skipping their geometry must leave every ring score unchanged.
	for distance in [361.0, 500.0, 899.0]:
		drops.append({"id": drops.size() + 1, "position": ORIGIN + Vector2(0, distance)})
	var distant = Arbiter.new()
	_choose(distant, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(distant._drop_target_id, ring._drop_target_id)
	assert_eq(distant.last_dirs, ring.last_dirs)
	assert_eq(distant.last_scores, ring.last_scores, "unreachable non-targets contribute exactly zero")


func _simulate(ticks: int, delta: float, label: String) -> Dictionary:
	var arb = Arbiter.new()
	var pos = ORIGIN
	var drops = _drops()
	var previous = Vector2.ZERO
	var just_collected = false
	var reversals = 0
	var distant_reversals = 0
	var collections = []
	for tick in range(ticks):
		var direction = _choose(arb, pos, drops, {"drop_pull": "target"})
		if not just_collected and previous != Vector2.ZERO and direction != Vector2.ZERO:
			if direction.dot(previous) < 0.0:
				reversals += 1
				if arb.last_target_dist < 0.0 or arb.last_target_dist > PICKUP_RIM + FINAL_APPROACH_REVERSAL_MARGIN:
					distant_reversals += 1
				print("%s_REVERSAL tick=%d t=%.4f previous=%s dir=%s target=%d dtg=%.6f switches=%d" % [
					label, tick + 1, tick * delta, str(previous), str(direction),
					arb._drop_target_id, arb.last_target_dist, arb.target_switches])
		var start = pos
		pos += direction * SPEED * delta
		var remaining = []
		for drop in drops:
			var closest = Geometry.get_closest_point_to_segment_2d(drop.position, start, pos)
			if closest.distance_to(drop.position) > PICKUP_RIM:
				remaining.append(drop)
		just_collected = remaining.size() < drops.size()
		drops = remaining
		if just_collected:
			collections.append([tick + 1, 24 - drops.size()])
		if ticks == 16 or tick % 10 == 0 or just_collected or tick == ticks - 1 \
				or (ticks == 240 and tick >= 23 and tick <= 33):
			print("%s_PATH tick=%d t=%.4f pos=%s dir=%s collected=%d target=%d dtg=%.6f switches=%d" % [
				label, tick + 1, (tick + 1) * delta, str(pos), str(direction), 24 - drops.size(),
				arb._drop_target_id, arb.last_target_dist, arb.target_switches])
		previous = direction
	print("%s_SUMMARY collected=%d reversals_between_collections=%d distant_reversals=%d pos=%s collections=%s" % [
		label, 24 - drops.size(), reversals, distant_reversals, str(pos), str(collections)])
	return {"collected": 24 - drops.size(), "distant_reversals": distant_reversals,
		"reversals": reversals, "collections": collections, "position": pos}


func test_target_collects_with_only_final_approach_reversals_16_ticks():
	var result = _simulate(16, 0.1, "DROP")
	assert_eq(result.distant_reversals, 0, "between collections, reversals require target dtg <= rim + 24 px")
	assert_true(result.collections.size() >= 3, "collects at multiple times, not just once")
	assert_true(result.collected >= 3, "steady collection during the simulation")
	assert_eq(result.collections, [[4, 1], [6, 2], [7, 3], [10, 4], [12, 5], [15, 6]],
		"collection timeline unchanged by linear fallback and segment pruning")
	assert_eq(result.reversals, 0)
	assert_true(result.position.distance_to(Vector2(1574.672607, 1319.999023)) < 0.001,
		"final position unchanged")


func test_target_collects_with_only_final_approach_reversals_60_hz():
	var result = _simulate(240, 1.0 / 60.0, "PHYSICS")
	assert_eq(result.distant_reversals, 0, "between collections, reversals require target dtg <= rim + 24 px")
	assert_true(result.collections.size() >= 6, "collects at multiple times over four seconds")
	assert_true(result.collected >= 6, "steady collection at physics frequency")
	assert_true(not result.collections.empty() and result.collections[0][0] <= 60, "first collection within one second")
	assert_eq(result.collections, [[24, 1], [33, 2], [50, 3], [52, 4], [86, 5], [91, 6],
		[125, 7], [130, 8], [131, 9], [151, 10], [154, 11], [189, 12], [194, 13],
		[222, 14], [223, 15], [237, 16]], "60 Hz collection timeline unchanged")
	assert_eq(result.reversals, 1, "the accepted final-approach sidestep is unchanged")
	assert_true(result.position.distance_to(Vector2(1328.112549, 1362.269897)) < 0.001,
		"60 Hz final position unchanged")


func test_other_reward_layouts_keep_linear_costs_under_target():
	for reward in [[ORIGIN + Vector2(180, 0), 4.0],
			[ORIGIN + Vector2(180, 0), 4.0, false],
			[ORIGIN + Vector2(180, 0), 4.0, false, 50.0],
			[ORIGIN + Vector2(180, 0), 4.0, false, 50.0, "floor_drop", 1]]:
		var scores = []
		for mode in ["linear", "target"]:
			var arb = Arbiter.new()
			arb.choose(ORIGIN, SPEED, 20.0, FAR, [], [reward], [], [],
				300.0, false, 100.0, 1.0, {"drop_pull": mode, "drop_quiet": true, "pickup_radius": 60.0})
			scores.append(arb.last_scores)
		assert_eq(scores[0], scores[1], "food/loot, tree, held reward unchanged")


func test_target_retains_identity_updates_position_and_requires_half_distance_to_switch():
	var arb = Arbiter.new()
	var drops = [{"id": 1, "position": ORIGIN + Vector2(200, 0)},
		{"id": 2, "position": ORIGIN + Vector2(-240, 0)}]
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1)
	assert_eq(arb.target_switches, 1)
	drops[0].position = ORIGIN + Vector2(220, 0)
	drops[1].position = ORIGIN + Vector2(-110, 0)
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1, "exactly half is not closer than half")
	assert_eq(arb._drop_target_pos, drops[0].position, "last position refreshes")
	assert_eq(arb.last_target_dist, 220.0)
	assert_eq(arb.target_switches, 1)
	drops[1].position = ORIGIN + Vector2(-109, 0)
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 2, "strictly closer than half switches")
	assert_eq(arb.target_switches, 2)
	drops.pop_back()
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1, "missing target is replaced")
	assert_eq(arb.target_switches, 3)


func test_target_ignores_quiet_gate_and_clears_when_leaving_mode():
	var arb = Arbiter.new()
	_choose(arb, ORIGIN, _drops(), {"drop_pull": "target"})
	_choose(arb, ORIGIN, _drops(), {"drop_pull": "target", "drop_quiet": false})
	assert_eq(arb._drop_target_id, 1)
	assert_eq(arb.target_switches, 1, "quiet gate does not change commitment")
	_choose(arb, ORIGIN, _drops(), {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1)
	assert_eq(arb.target_switches, 1)
	_choose(arb, ORIGIN, _drops(), {"drop_pull": "linear"})
	assert_eq(arb.last_target_dist, -1.0, "leaving target mode clears telemetry")
	assert_eq(arb.last_target_kind, "none")


func test_target_collected_inside_rim_and_no_remaining_drops_clear():
	var arb = Arbiter.new()
	var drops = [{"id": 1, "position": ORIGIN + Vector2(150, 0)},
		{"id": 2, "position": ORIGIN + Vector2(-200, 0)}]
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	_choose(arb, ORIGIN + Vector2(100, 0), drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 2, "inside rim no longer a target")
	_choose(arb, ORIGIN, [], {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, -1)
	assert_eq(arb.last_target_dist, -1.0)


func test_target_outside_steering_range_remains_scored_and_keeps_moving():
	var arb = Arbiter.new()
	var drops = [{"id": 1, "position": ORIGIN + Vector2(150, 0)},
		{"id": 2, "position": ORIGIN + Vector2(600, 0)}]
	_choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1)
	# All-map selection retains this target; its approach remains scored even
	# though only the other drop is in the local pass-through reward list.
	drops[0].position = ORIGIN + Vector2(1000, 0)
	var choice = _choose(arb, ORIGIN, drops, {"drop_pull": "target"})
	assert_eq(arb._drop_target_id, 1, "whole-map commitment survives leaving the local horizon")
	assert_eq(arb.last_target_dist, 1000.0)
	assert_eq(arb.target_switches, 1)
	assert_true(choice != Vector2.ZERO, "in-range replacement keeps the bot moving")
	assert_true(choice.x > 0.0, "moves toward the replacement drop")


func test_target_uses_reward_value_and_only_target_approaches_but_all_can_be_taken():
	var arb = Arbiter.new()
	var rewards = [FloorDrop.reward(ORIGIN + Vector2(400, 0), 1.0, 1.0, 1),
		FloorDrop.reward(ORIGIN + Vector2(500, 0), 2.0, 1.0, 2)]
	var profile = {"drop_pull": "target", "drop_quiet": true, "pickup_radius": 60.0}
	arb.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0, profile)
	assert_eq(arb._drop_target_id, 2, "distance / reward value picks farther valuable drop")
	var both = arb.last_scores.duplicate()
	var solo = Arbiter.new()
	solo.choose(ORIGIN, SPEED, 20.0, FAR, [], [rewards[1]], [], [], 300.0, false, 100.0, 1.0, profile)
	assert_eq(both, solo.last_scores, "non-target outside projected rim adds no approach")
	# Establish a right-side target, then add a left-side pass-through drop.
	# Give both comparisons the same continuity state so only collection differs.
	var pass_through = FloorDrop.reward(ORIGIN + Vector2(-260, 0), 1.0, 1.0, 3)
	rewards.append(pass_through)
	arb.last_dir = Vector2.ZERO
	arb.choose(ORIGIN, SPEED, 20.0, FAR, [], rewards, [], [], 300.0, false, 100.0, 1.0, profile)
	assert_eq(arb._drop_target_id, 2, "260 is not less than half of 500")
	assert_true(arb.last_scores[12] < solo.last_scores[12], "non-target crossing still earns taken bonus")
	var taken = solo.last_scores[12] - arb.last_scores[12]
	assert_true(abs(taken - pass_through[1] * arb.pickup_taken) < 0.000001,
		"crossing earns exactly the collection bonus with equal last_dir")
	print("PASS_THROUGH last_dir=(0, 0) solo_left=%.6f crossed_left=%.6f taken=%.6f target=%d" %
		[solo.last_scores[12], arb.last_scores[12], taken, arb._drop_target_id])
