extends "res://mod/tests/test_base.gd"

const RunRecorder = preload("res://mod/Ellie-BrotatoBot/core/run_recorder.gd")
const BotPaths = preload("res://mod/Ellie-BrotatoBot/core/bot_paths.gd")
const BotConfig = preload("res://mod/Ellie-BrotatoBot/core/bot_config.gd")
const PlanFile = preload("res://mod/Ellie-BrotatoBot/core/plan_file.gd")

const HEADER = {"character_id": "character_well_rounded", "danger": 0, "zone": 2}


# A fresh, empty directory under the test project's user data dir.
func _make_root():
	var root = OS.get_user_data_dir().plus_file("test-run-recorder-%d" % OS.get_ticks_usec())
	var d = Directory.new()
	if d.make_dir_recursive(root) != OK:
		failures.append("could not create temp root %s" % root)
	return root


# Removes root and everything under it (two levels are enough: root/runs/*.jsonl).
func _remove_tree(path):
	var d = Directory.new()
	if d.open(path) != OK:
		return
	d.list_dir_begin(true, true)
	var f = d.get_next()
	while f != "":
		var child = path.plus_file(f)
		if d.current_is_dir():
			_remove_tree(child)
		else:
			d.remove(child)
		f = d.get_next()
	d.list_dir_end()
	d.remove(path)


# Every line of the file, parsed; a line that does not parse as a JSON object
# is recorded as a failure and returned as null.
func _read_lines(path):
	var out = []
	var f = File.new()
	if f.open(path, File.READ) != OK:
		failures.append("cannot open %s" % path)
		return out
	var text = f.get_as_text()
	f.close()
	for line in text.split("\n", false):
		var parsed = JSON.parse(line)
		if parsed.error != OK or typeof(parsed.result) != TYPE_DICTIONARY:
			failures.append("line does not parse as a JSON object: %s" % line)
			out.append(null)
		else:
			out.append(parsed.result)
	return out


func test_start_run_creates_file_with_header_line():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	var run_id = rec.start_run(HEADER.duplicate())
	assert_eq(typeof(run_id), TYPE_STRING, "start_run returns a String")
	assert_eq(rec.run_id, run_id, "run_id property")
	var re = RegEx.new()
	re.compile("^\\d{8}-\\d{6}-well_rounded-d0$")
	assert_true(re.search(str(run_id)) != null, "run_id format: %s" % str(run_id))
	var path = root.plus_file("runs").plus_file("%s.jsonl" % str(run_id))
	assert_true(File.new().file_exists(path), "run file exists at %s" % path)
	# Read while the recorder still holds the file open: proves the flush.
	var lines = _read_lines(path)
	assert_eq(lines.size(), 1, "one line before any event")
	if lines.size() >= 1 and lines[0] != null:
		assert_eq(lines[0].get("kind"), "header", "kind")
		assert_eq(lines[0].get("run_id"), run_id, "header carries run_id")
		assert_eq(lines[0].get("character_id"), "character_well_rounded", "header keeps character_id")
		assert_true(lines[0].has("t"), "header has t")
	rec.end_run({"outcome": "test"})
	_remove_tree(root)


func test_events_append_valid_json_lines():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	var run_id = rec.start_run(HEADER.duplicate())
	rec.event("damage", {"wave": 1, "source": "baby_alien", "amount": 3, "hp_after": 7})
	OS.delay_msec(5)
	rec.snapshot({"wave": 1, "hp": 7, "max_hp": 10})
	OS.delay_msec(5)
	rec.event("wave_end", {"wave": 1, "hp": 7, "gold": 30, "damage_taken": 3, "kills": 12})
	var path = root.plus_file("runs").plus_file("%s.jsonl" % str(run_id))
	var lines = _read_lines(path)
	assert_eq(lines.size(), 4, "header plus three events, read while open")
	var kinds = []
	var last_t = -1.0
	for l in lines:
		if l == null:
			continue
		kinds.append(l.get("kind"))
		var t = l.get("t")
		assert_true(typeof(t) == TYPE_REAL or typeof(t) == TYPE_INT, "t is a number")
		if typeof(t) == TYPE_REAL or typeof(t) == TYPE_INT:
			assert_true(float(t) >= last_t, "t non-decreasing (%s after %s)" % [str(t), str(last_t)])
			last_t = float(t)
	assert_eq(kinds, ["header", "damage", "snapshot", "wave_end"], "kinds in order")
	if lines.size() == 4 and lines[1] != null:
		assert_eq(lines[1].get("source"), "baby_alien", "event data keys merged into the line")
	rec.end_run({"outcome": "test"})
	_remove_tree(root)


func test_end_run_writes_end_and_closes():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	var run_id = rec.start_run(HEADER.duplicate())
	assert_true(rec.is_open(), "open after start_run")
	rec.end_run({"outcome": "death", "wave": 3, "hp": 0, "gold": 12})
	assert_false(rec.is_open(), "closed after end_run")
	# Events after end_run are dropped, not appended and not an error.
	rec.event("snapshot", {"wave": 3})
	var path = root.plus_file("runs").plus_file("%s.jsonl" % str(run_id))
	var lines = _read_lines(path)
	assert_eq(lines.size(), 2, "header and end only")
	if lines.size() > 0 and lines[0] != null:
		assert_eq(lines[0].get("zone"), 2.0, "header records actual zone (JSON float)")
	if lines.size() == 2 and lines[1] != null:
		assert_eq(lines[1].get("kind"), "end", "last kind")
		assert_eq(lines[1].get("outcome"), "death", "outcome")
		assert_eq(lines[1].get("wave"), 3.0, "wave (JSON numbers read back as floats)")
	_remove_tree(root)


func test_default_paths_derive_from_bot_paths_root():
	assert_eq(BotPaths.ROOT, "user://brotato-bot", "ROOT")
	assert_eq(BotConfig.DEFAULT_PATH, BotPaths.ROOT + "/config.json", "config path")
	assert_eq(PlanFile.DEFAULT_PATH, BotPaths.ROOT + "/plan.json", "plan path")


# Dictionaries compare by reference in Godot 3: compare sorted JSON instead.
func _j(d):
	return JSON.print(d, "", true)


func test_shop_event_shape():
	var e = RunRecorder.shop_event(5, "buy", "item_anvil", 40, 12.5, "rule", 63)
	assert_eq(_j(e), _j({"wave": 5, "action": "buy", "item_id": "item_anvil", "price": 40, "score": 12.5,
		"source": "rule", "gold_after": 63}), "buy")
	var go = RunRecorder.shop_event(5, "go", null, null, null, "rule", 23)
	assert_eq(_j(go), _j({"wave": 5, "action": "go", "item_id": null, "price": null, "score": null,
		"source": "rule", "gold_after": 23}), "go has nulls")
	var reroll = RunRecorder.shop_event(5.0, "reroll", null, 3.0, null, "haiku", 60.0)
	assert_eq(reroll.wave, 5, "wave int")
	assert_eq(reroll.price, 3, "price int")
	assert_eq(reroll.gold_after, 60, "gold int")
	var s = RunRecorder.shop_event(1, "lock", "weapon_x", 30, 28, "rule", 10)
	assert_eq(s.score, 28.0, "score float")


func test_checkpoint_event_carries_wave_for_every_outcome():
	for result in [
		{"id": "", "action": null, "applied": "skip", "reason": "asking_disabled"},
		{"id": "", "action": null, "applied": "skip", "reason": "no_sidecar"},
		{"id": "cp-10", "action": "revise_plan", "applied": "revise_plan", "reason": ""},
		{"id": "cp-10", "action": null, "applied": "timeout", "reason": "timeout"},
	]:
		var e = RunRecorder.checkpoint_event(10, result)
		assert_eq(e.wave, 10, "current wave independent of delayed wave_end")
		assert_eq(e.keys().size(), 5, "wave plus four checkpoint fields")
		for key in result:
			assert_eq(e[key], result[key], "preserves " + key)
		assert_false(result.has("wave"), "input unchanged")
	var replaced = RunRecorder.checkpoint_event(10, {"wave": 9})
	assert_eq(replaced.wave, 10, "write-time wave overrides stale data")


func test_continues_only_the_same_profile_and_character():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	assert_false(rec.continues(1, "character_well_rounded"), "nothing open")
	rec.start_run({"character_id": "character_well_rounded", "danger": 0, "profile_id": 1})
	assert_true(rec.continues(1, "character_well_rounded"), "same run")
	assert_true(rec.continues(1.0, "character_well_rounded"), "float profile id")
	assert_false(rec.continues(0, "character_well_rounded"), "other profile")
	assert_false(rec.continues(1, "character_mage"), "other character")
	rec.end_run({"outcome": "abandoned"})
	assert_false(rec.continues(1, "character_well_rounded"), "closed")
	_remove_tree(root)


func test_launch_event_carries_the_five_launch_fields():
	var e = RunRecorder.launch_event({"token": "t1", "character_id": "character_old",
		"starting_weapon": "any", "danger": 4, "zone": 2.0, "created_at": "x"})
	assert_eq(e.keys().size(), 5, "only the five fields")
	assert_eq(e.token, "t1", "token")
	assert_eq(e.character_id, "character_old", "character_id")
	assert_eq(e.starting_weapon, "any", "starting_weapon")
	assert_eq(e.danger, 4, "danger an int")
	assert_eq(e.zone, 2, "zone")
	assert_eq(typeof(e.zone), TYPE_INT, "zone an int")
	assert_eq(RunRecorder.launch_event({}).zone, 0, "legacy zone default")


func test_offer_event_and_item_types():
	var item = RunRecorder.offer_item("item_anvil", 2.0, 40.0, 7, true)
	assert_eq(item.id, "item_anvil", "id")
	assert_eq(item.tier, 2, "tier is an int")
	assert_eq(item.price, 40, "price is an int")
	assert_eq(item.score, 7.0, "score is a float")
	assert_true(item.locked, "locked")
	var e = RunRecorder.offer_event(3.0, 2, 120.0, [item])
	assert_eq(e.wave, 3, "wave")
	assert_eq(e.view, 2, "view")
	assert_eq(e.gold, 120, "gold")
	assert_eq(e.items.size(), 1, "items")
	assert_eq(e.keys().size(), 4, "wave, view, gold, items")


func test_crate_and_build_events():
	var c = RunRecorder.crate_event(5, "item_bag", "recycle", 3)
	assert_eq(c.wave, 5, "wave")
	assert_eq(c.item_id, "item_bag", "item_id")
	assert_eq(c.action, "recycle", "action")
	assert_eq(c.score, 3.0, "score is a float")
	var b = RunRecorder.build_event(["weapon_rock_1"], ["item_bag"])
	assert_eq(b.weapons, ["weapon_rock_1"], "weapons")
	assert_eq(b.items, ["item_bag"], "items")


func test_mats_counts_floor_and_finds_nearest():
	var m = RunRecorder.mats([
		{"position": Vector2(100, 0), "value": 1, "unattached": true},
		{"position": Vector2(30, 40), "value": 4, "unattached": false},
		{"position": Vector2(-300, 0), "value": 2, "unattached": true},
	], Vector2(0, 0), 12.0)
	assert_eq(m.floor, 3, "floor")
	assert_eq(m.floor_value, 7, "value differs from object count")
	assert_eq(m.unattached, 2, "attracted material stays in floor/value/nearest")
	assert_eq(m.bag, 12, "bag")
	assert_eq(m.nearest, 50, "nearest is the 3-4-5 pickup")
	assert_eq(m.keys().size(), 5, "exact snapshot shape")
	var none = RunRecorder.mats([], Vector2(5, 5), 0)
	assert_eq(none.floor, 0, "no pickups")
	assert_eq(none.floor_value, 0, "no floor value")
	assert_eq(none.unattached, 0, "none unattached")
	assert_eq(none.bag, 0, "empty bag")
	assert_eq(none.nearest, -1, "nearest -1 when none")


func test_wave_materials_and_trees_have_exact_integer_shapes():
	var m = RunRecorder.wave_materials(3.0, 7.0, 2.0, 9.0, 123.0, 104.0)
	assert_eq(m.floor_count, 3, "count")
	assert_eq(m.floor_value, 7, "value")
	assert_eq(m.bag_before, 2, "bag before cleanup")
	assert_eq(m.bag_after, 9, "bag after cleanup")
	assert_eq(m.collected_value, 19, "wallet gain nested in materials")
	assert_eq(m.keys().size(), 5, "exact materials shape")
	assert_eq(RunRecorder.wave_materials(0, 0, 0, null, 4, 9).collected_value, -5,
		"net spending may produce a negative delta")
	assert_eq(RunRecorder.wave_materials(1, 2, 0, null).bag_after, null, "unknown is not zero")
	var trees = RunRecorder.wave_trees(5.0, 3.0, 2.0)
	assert_eq(trees.spawned, 5, "spawned lives, including pooled respawns")
	assert_eq(trees.felled, 3, "combat deaths")
	assert_eq(trees.alive, 2, "before cleanup")
	assert_eq(trees.keys().size(), 3, "exact trees shape")


func test_wave_end_waits_for_observed_bag_and_writes_once():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	var rid = rec.start_run(HEADER)
	var data = {"wave": 1,
		"materials": RunRecorder.wave_materials(3, 7, 2, null, 123, 104),
		"trees": RunRecorder.wave_trees(5, 3, 2)}
	rec.begin_wave_end(data)
	data.materials.floor_value = 999
	var path = root.plus_file("runs").plus_file(rid + ".jsonl")
	assert_eq(_read_lines(path).size(), 1, "not emitted before bag observed")
	rec.finish_wave_end(9.0)
	rec.finish_wave_end(20)
	rec.end_run({"outcome": "won"})
	var lines = _read_lines(path)
	assert_eq(lines.size(), 3, "header, one wave_end, end")
	assert_eq(lines[1].kind, "wave_end", "event")
	assert_eq(int(lines[1].materials.floor_value), 7, "captured before cleanup; independent copy")
	assert_eq(int(lines[1].materials.bag_after), 9, "observed bag")
	assert_eq(int(lines[1].materials.collected_value), 19, "nested wallet gain preserved")
	assert_false(lines[1].has("collected_value"), "no misplaced top-level field")
	assert_eq(int(lines[1].trees.alive), 2, "cleanup does not rewrite live count")
	_remove_tree(root)


func test_run_close_flushes_unobserved_wave_end_before_end():
	var root = _make_root()
	var rec = RunRecorder.new(root)
	var rid = rec.start_run(HEADER)
	rec.begin_wave_end({"wave": 1, "materials": RunRecorder.wave_materials(2, 4, 1, null)})
	rec.end_run({"outcome": "quit"})
	var lines = _read_lines(root.plus_file("runs").plus_file(rid + ".jsonl"))
	assert_eq(lines.size(), 3, "pending wave retained")
	assert_eq(lines[1].kind, "wave_end", "wave before end")
	assert_eq(lines[1].materials.bag_after, null, "unknown bag on terminal wave or early exit")
	assert_eq(lines[2].kind, "end", "end remains last")
	_remove_tree(root)

