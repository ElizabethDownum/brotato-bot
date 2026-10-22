extends "res://mod/tests/test_base.gd"

const RunRecorder = preload("res://mod/Ellie-BrotatoBot/core/run_recorder.gd")
const BotPaths = preload("res://mod/Ellie-BrotatoBot/core/bot_paths.gd")
const BotConfig = preload("res://mod/Ellie-BrotatoBot/core/bot_config.gd")
const PlanFile = preload("res://mod/Ellie-BrotatoBot/core/plan_file.gd")

const HEADER = {"character_id": "character_well_rounded", "danger": 0}


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
	if lines.size() == 2 and lines[1] != null:
		assert_eq(lines[1].get("kind"), "end", "last kind")
		assert_eq(lines[1].get("outcome"), "death", "outcome")
		assert_eq(lines[1].get("wave"), 3.0, "wave (JSON numbers read back as floats)")
	_remove_tree(root)


func test_default_paths_derive_from_bot_paths_root():
	assert_eq(BotPaths.ROOT, "user://brotato-bot", "ROOT")
	assert_eq(BotConfig.DEFAULT_PATH, BotPaths.ROOT + "/config.json", "config path")
	assert_eq(PlanFile.DEFAULT_PATH, BotPaths.ROOT + "/plan.json", "plan path")
