extends "res://mod/tests/test_base.gd"

const Steering = preload("res://mod/Ellie-BrotatoBot/core/steering_overrides.gd")
const PlanFile = preload("res://mod/Ellie-BrotatoBot/core/plan_file.gd")
const Recorder = preload("res://mod/Ellie-BrotatoBot/core/run_recorder.gd")


func test_baseline_and_overrides_do_not_mutate_character_row():
	var base = {"gold": 0.8, "caution": 1.0, "tree_value": 0.0, "sweep": 1.0,
		"if_melee": {"caution": 1.4}}
	var defaults = Steering.resolve(base, {})
	assert_eq(defaults.gold_value, 0.8, "Well Rounded baseline material value")
	assert_eq(defaults.tree_value, 0.0, "baseline tree reward")
	assert_eq(defaults.sweep, 1.0, "baseline dormant sweep")
	assert_eq(defaults.sweep_radius, 420.0, "quiet radius")
	assert_eq(defaults.stand_continuity, -1.2, "standing cost")
	assert_eq(defaults.tree_policy, "auto", "baseline policy")
	assert_eq(defaults.drop_pull, "linear", "default preserves floor scoring")
	assert_eq(Steering.resolve(base, {"drop_pull": "target"}).drop_pull, "target", "opt in")
	var out = Steering.resolve(base, {"gold_value": 1.8, "tree_value": 5,
		"sweep": 1.5, "sweep_radius": 360, "stand_continuity": -0.2})
	assert_eq(out.gold, 1.8, "public gold_value maps to existing row gold")
	assert_eq(out.tree_value, 5.0, "tree override")
	assert_eq(out.sweep, 1.5, "sweep override")
	assert_eq(out.sweep_radius, 360.0, "radius override")
	assert_eq(out.stand_continuity, -0.2, "standing cost override")
	assert_eq(out.caution, 1.0, "caution preserved")
	out.if_melee.caution = 9.0
	assert_eq(base.if_melee.caution, 1.4, "deep copy")
	assert_eq(base.gold, 0.8, "base unchanged")
	assert_eq(Steering.resolve({"gold": 1.8}, {}).gold_value, 1.8, "Old retains own value")


func test_explicit_character_row_survives_normalization():
	var well_rounded = {"gold": 0.8, "caution": 1.0, "tree_value": 0.0, "sweep": 1.0}
	var old = {"gold": 1.8, "caution": 0.7}
	assert_false(Steering.resolve(well_rounded, {}, "character_well_rounded").has_explicit_row,
		"Well Rounded baseline retains former empty-row CLI applicability")
	assert_true(Steering.resolve(old, {}, "character_old").has_explicit_row,
		"Old retains explicit character row")
	assert_false(Steering.resolve({}, {}, "character_unknown").has_explicit_row,
		"normalization does not create an explicit row")
	var out = Steering.resolve(well_rounded, {"gold_value": 3.0, "sweep": 1.5},
		"character_well_rounded")
	assert_true(out.has_explicit_row, "plan activates Well Rounded row")
	assert_eq(out.gold, 3.0, "plan gold baseline applied")
	assert_eq(out.sweep, 1.5, "plan sweep applied")


func test_builder_resolved_baseline_prefers_plan_over_cli():
	var row = {"gold_mode": "builder"}
	assert_eq(Steering.resolve(row, {}).gold_value, 0.8, "Builder default economy baseline")
	row.gold = 2.0
	assert_eq(Steering.resolve(row, {}).gold_value, 2.0, "CLI baseline without plan")
	var out = Steering.resolve(row, {"gold_value": 3.0})
	assert_eq(out.gold, 3.0, "plan baseline replaces CLI before Builder economy phase")
	assert_eq(out.gold_mode, "builder", "Builder phase mode retained")
	assert_eq(Steering.resolve(row, {"gold_value": 0}).gold, 0.0, "explicit zero beats CLI")


func test_tree_policies():
	var row = {"tree_value": 6.0}
	assert_eq(Steering.resolve(row, {"tree_policy": "auto"}).tree_value, 6.0, "auto keeps row")
	assert_eq(Steering.resolve(row, {"tree_policy": "seek"}).tree_value, 4.0, "seek defaults to 4")
	assert_eq(Steering.resolve(row, {"tree_policy": "seek", "tree_value": 0}).tree_value,
		0.0, "seek respects explicit zero")
	var preserve = Steering.resolve(row, {"tree_policy": "preserve", "tree_value": 9, "sweep": 1.5})
	assert_eq(preserve.tree_value, 0.0, "preserve wins over explicit reward")
	assert_eq(preserve.sweep, 1.5, "preserve changes nothing else")


func test_validation_and_unknown_keys_are_ignored_with_warning():
	assert_true(PlanFile.value_ok("steering", {}), "empty allowed")
	for k in ["tree_value", "sweep", "sweep_radius", "gold_value", "stand_continuity"]:
		assert_true(PlanFile.value_ok("steering", {k: 2}), k + " integer")
		assert_true(PlanFile.value_ok("steering", {k: 1.5}), k + " fractional")
		for bad in [true, "2", null, [], {}]:
			assert_false(PlanFile.value_ok("steering", {k: bad}), k + " wrong type")
	for p in ["auto", "seek", "preserve"]:
		assert_true(PlanFile.value_ok("steering", {"tree_policy": p}), "policy " + p)
	for bad in ["avoid", 1, true, null]:
		assert_false(PlanFile.value_ok("steering", {"tree_policy": bad}), "bad policy")
	for mode in ["linear", "target"]:
		assert_true(PlanFile.value_ok("steering", {"drop_pull": mode}), "valid drop mode")
	for bad in ["auto", 1, true, null, [], {}]:
		assert_false(PlanFile.value_ok("steering", {"drop_pull": bad}), "bad drop mode")
	assert_false(PlanFile.value_ok("steering", []), "object required")
	assert_false(PlanFile.value_ok("steering", {"unknown": 2}), "unknown rejected in patch")
	var out = Steering.resolve({}, {"unknown": 99, "tree_value": "bad", "sweep": 1.5})
	assert_false(out.has("unknown"), "unknown dropped with warning")
	assert_eq(out.tree_value, 0.0, "bad type ignored with warning")
	assert_eq(out.sweep, 1.5, "valid sibling retained")


func test_plan_patch_merges_and_refreshes_cached_steering():
	var dir = "user://test-steering-%d" % OS.get_ticks_usec()
	var path = dir.plus_file("plan.json")
	var ch = "character_well_rounded"
	assert_eq(PlanFile.apply_patch(path, ch, {"steering": {"tree_policy": "seek", "sweep": 1.5,
		"drop_pull": "target"}}, "s"),
		OK, "initial plan")
	var first = PlanFile.load_cached(path)
	assert_eq(Steering.resolve({}, Steering.from_plan(first, ch)).tree_value, 4.0, "first resolution")
	assert_eq(Steering.from_plan(first, "character_old").size(), 0, "character match required")
	assert_eq(Steering.from_plan(null, ch).size(), 0, "absent plan")
	assert_eq(PlanFile.apply_patch(path, ch, {"steering": {"sweep": 2.5}}, "s"), OK, "checkpoint patch")
	var overrides = Steering.from_plan(PlanFile.load_cached(path), ch)
	assert_eq(overrides.tree_policy, "seek", "one-level merge retains policy")
	assert_eq(overrides.sweep, 2.5, "same-second update visible")
	assert_eq(overrides.drop_pull, "target", "drop mode survives plan load and merge")
	assert_eq(PlanFile.apply_patch(path, ch, {"steering": {"sweep": true}}, "s"), OK, "bad patch dropped")
	assert_eq(Steering.from_plan(PlanFile.load_cached(path), ch).sweep, 2.5, "invalid patch preserves value")
	Directory.new().remove(path)
	Directory.new().remove(dir)


func test_loaded_plan_filters_bad_entries_before_resolution():
	var dir = "user://test-steering-load-%d" % OS.get_ticks_usec()
	var path = dir.plus_file("plan.json")
	var ch = "character_well_rounded"
	assert_eq(PlanFile.save(path, {"plan_id": "s", "character_id": ch,
		"plan": {"steering": {"sweep": 1.5, "unknown": 2, "tree_value": true}}}), OK, "raw plan")
	var loaded = PlanFile.load_cached(path)
	var overrides = Steering.from_plan(loaded, ch)
	assert_eq(overrides.keys().size(), 1, "only usable siblings reach event/live resolution")
	assert_eq(overrides.sweep, 1.5, "valid value retained")
	assert_eq(Steering.resolve({}, overrides).tree_value, 0.0, "bad value uses default")
	Directory.new().remove(path)
	Directory.new().remove(dir)


func test_steering_event_follows_header_and_copies_applied_values():
	var root = "user://test-steering-event-%d" % OS.get_ticks_usec()
	var rec = Recorder.new(root)
	var ch = "character_well_rounded"
	var rid = rec.start_run({"character_id": ch, "danger": 0})
	var overrides = {"tree_policy": "seek", "sweep": 1.5, "drop_pull": "target"}
	var row = Steering.resolve({"gold": 0.8, "caution": 1.0}, overrides)
	var event = Steering.event(ch, overrides, row, 0.8, 1.0)
	rec.event("steering", event)
	overrides.sweep = 9
	assert_eq(event.overrides.sweep, 1.5, "applied overrides copied")
	assert_eq(event.resolved.keys().size(), 9, "all seven keys plus material value and caution")
	assert_eq(event.resolved.drop_pull, "target", "drop mode in steering event")
	assert_eq(event.resolved.tree_value, 4.0, "effective policy reward")
	assert_eq(event.resolved.material_value, 0.8, "material value")
	rec.end_run({"outcome": "test"})
	var path = root.plus_file("runs").plus_file(rid + ".jsonl")
	var f = File.new()
	assert_eq(f.open(path, File.READ), OK, "run readable")
	assert_eq(JSON.parse(f.get_line()).result.kind, "header", "header first")
	var recorded = JSON.parse(f.get_line()).result
	assert_eq(recorded.kind, "steering", "steering immediately after header")
	assert_eq(recorded.character_id, ch, "source character")
	assert_eq(recorded.resolved.sweep, 1.5, "resolved sweep serialized")
	f.close()
	Directory.new().remove(path)
	Directory.new().remove(root.plus_file("runs"))
	Directory.new().remove(root)
