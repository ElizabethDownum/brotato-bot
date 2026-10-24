extends "res://mod/tests/test_base.gd"

const Tracker = preload("res://mod/Ellie-BrotatoBot/core/loot_tracker.gd")
const Recorder = preload("res://mod/Ellie-BrotatoBot/core/run_recorder.gd")


func test_loot_snapshot_empty_nearest_and_strict_pickup_range():
	var empty = Tracker.snapshot([], Vector2.ZERO, 900.0)
	assert_eq(empty.alive, 0)
	assert_eq(empty.nearest, -1.0)
	assert_false(empty.in_range)
	var near = Tracker.snapshot([Vector2(1000, 0), Vector2(300, 400)], Vector2.ZERO, 900.0)
	assert_eq(near.alive, 2)
	assert_eq(near.nearest, 500.0)
	assert_true(near.in_range)
	assert_false(Tracker.snapshot([Vector2(900, 0)], Vector2.ZERO, 900.0).in_range)


func test_loot_life_closest_once_and_pooled_respawn():
	var tracker = Tracker.new()
	tracker.spawn(42, 3, 5.0, 700.0)
	tracker.observe(42, 240.5)
	tracker.spawn(42, 3, 6.0, 500.0) # repeated observation retains true spawn
	var event = tracker.finish(42, 12.0, "killed")
	var expected = {"alien_id": 42, "wave": 3, "spawn_t": 5.0, "end_t": 12.0,
		"closest": 240.5, "outcome": "killed"}
	for key in expected:
		assert_eq(event[key], expected[key], key)
	assert_eq(tracker.finish(42, 13.0, "escaped"), null, "no duplicate event")
	tracker.spawn(42, 3, 15.0, 800.0)
	assert_eq(tracker.finish(42, 18.0, "escaped").spawn_t, 15.0, "pooled life starts fresh")


func test_loot_outcome_distinguishes_enemy_cap_cull_from_kill():
	assert_eq(Tracker.outcome(false, true, true), "killed")
	assert_eq(Tracker.outcome(false, true, false), "escaped", "cap cull default die args")
	assert_eq(Tracker.outcome(false, false, true), "escaped")
	assert_eq(Tracker.outcome(true, true, true), "wave_end")


func test_loot_missing_and_wave_cleanup_emit_once():
	var tracker = Tracker.new()
	tracker.spawn(1, 8, 1.0, 600.0)
	tracker.spawn(2, 8, 2.0, 400.0)
	var missing = tracker.missing([2], 4.0)
	assert_eq(missing.size(), 1)
	assert_eq(missing[0].outcome, "escaped")
	var cleanup = tracker.finish_wave(60.0)
	assert_eq(cleanup.size(), 1)
	assert_eq(cleanup[0].outcome, "wave_end")
	assert_eq(cleanup[0].alien_id, 2)
	assert_eq(tracker.finish_wave(60.0), [], "base cleanup cannot emit duplicates")


func test_loot_event_uses_existing_run_recorder_path():
	var root = "user://test-loot-%d" % OS.get_ticks_usec()
	var rec = Recorder.new(root)
	var rid = rec.start_run({"character_id": "character_well_rounded", "danger": 1})
	var tracker = Tracker.new()
	tracker.spawn(1, 2, 4.0, 510.0)
	rec.event("loot_alien", tracker.finish(1, 9.0, "killed"))
	rec.end_run({"outcome": "test"})
	var path = root.plus_file("runs").plus_file(rid + ".jsonl")
	var f = File.new()
	assert_eq(f.open(path, File.READ), OK)
	f.get_line()
	var event = JSON.parse(f.get_line()).result
	assert_eq(event.kind, "loot_alien")
	assert_eq(event.spawn_t, 4.0)
	assert_eq(event.end_t, 9.0)
	assert_eq(event.outcome, "killed")
	assert_true(event.has("t"), "recorder run timestamp retained")
	f.close()
	Directory.new().remove(path)
	Directory.new().remove(root.plus_file("runs"))
	Directory.new().remove(root)
