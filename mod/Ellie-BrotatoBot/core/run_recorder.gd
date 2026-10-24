extends Reference
# JSON Lines recorder for one run. Pure logic: takes an explicit root directory
# so it runs in the headless test project. No class_name -- callers preload it.
#
#   var rec = RunRecorder.new(BotPaths.ROOT)
#   rec.start_run({"character_id": "character_well_rounded", "danger": 0, ...})
#   rec.event("damage", {...}); rec.snapshot({...}); rec.end_run({...})
#
# Writes <root_dir>/runs/<run_id>.jsonl, one JSON object per line:
#   {"t": ms_since_start_run, "kind": kind, ...data}
# The file stays open and is flushed after every line, so a crash or an
# external reader (the Python harness) sees every completed line. Events sent
# while no run is open are dropped silently.
#
# run_id is YYYYMMDD-HHMMSS-<character_id without "character_">-d<danger>,
# local time from OS.get_datetime().

var run_id = ""
var header = {}   # the open run's header line ({} when none)

var _root_dir = ""
var _file = null
var _start_ms = 0


func _init(root_dir):
	_root_dir = str(root_dir)


func is_open():
	return _file != null


# Opens a new run file and writes the header line (header plus run_id).
# Any run still open is closed first without an end line. Returns run_id, or
# "" when the file cannot be created (recording is then disabled).
func start_run(header):
	if _file != null:
		_close()
	run_id = make_run_id(header.get("character_id", ""), header.get("danger", 0), OS.get_datetime())
	var dir_path = _root_dir.plus_file("runs")
	var d = Directory.new()
	if not d.dir_exists(dir_path) and d.make_dir_recursive(dir_path) != OK:
		push_warning("RunRecorder: cannot create %s; recording disabled" % dir_path)
		run_id = ""
		return ""
	var path = dir_path.plus_file(run_id + ".jsonl")
	var f = File.new()
	var err = f.open(path, File.WRITE)
	if err != OK:
		push_warning("RunRecorder: cannot open %s (error %d); recording disabled" % [path, err])
		run_id = ""
		return ""
	_file = f
	_start_ms = OS.get_ticks_msec()
	var h = header.duplicate(true)
	h["run_id"] = run_id
	self.header = h
	event("header", h)
	return run_id


# Appends {"t", "kind", ...data}. data keys named "t" or "kind" are overwritten.
func event(kind, data):
	if _file == null:
		return
	var line = data.duplicate(true)
	line["t"] = OS.get_ticks_msec() - _start_ms
	line["kind"] = str(kind)
	_file.store_line(JSON.print(line))
	_file.flush()


func snapshot(data):
	event("snapshot", data)


# Writes the "end" line and closes the file.
func end_run(outcome):
	if _file == null:
		return
	event("end", outcome)
	_close()


func _close():
	_file.close()
	_file = null
	header = {}


# True when a run file is open and its header names this profile and
# character: only then may a later wave continue it (final review I2).
func continues(profile_id, character_id) -> bool:
	return is_open() and same_run(header, profile_id, character_id)


static func same_run(h, profile_id, character_id) -> bool:
	if typeof(h) != TYPE_DICTIONARY or not h.has("profile_id") or h.get("profile_id") == null:
		return false
	return int(h.profile_id) == int(profile_id) and str(h.get("character_id", "")) == str(character_id)


# One shop event (spec 7.1): every bot buy / reroll / lock / ban / GO.
#   wave, price, gold_after  ints (price null for go; the reroll's cost for reroll)
#   item_id                  String, or null (reroll / go)
#   score                    float, or null (reroll / ban / go)
#   source                   "rule" | "haiku" (the sidecar's applied answer)
static func shop_event(wave, action, item_id, price, score, source, gold_after) -> Dictionary:
	return {
		"wave": int(wave),
		"action": str(action),
		"item_id": null if item_id == null else str(item_id),
		"price": null if price == null else int(price),
		"score": null if score == null else float(score),
		"source": str(source),
		"gold_after": int(gold_after),
	}


# The launch event (spec: the launcher consumed launch.json): which launch the
# run came from, so the harness can tie the run to the plan's token.
static func launch_event(launch) -> Dictionary:
	return {
		"token": str(launch.get("token", "")),
		"character_id": str(launch.get("character_id", "")),
		"starting_weapon": str(launch.get("starting_weapon", "")),
		"danger": int(launch.get("danger", 0)),
	}


# YYYYMMDD-HHMMSS-<character without "character_">-d<danger>.
# dt is an OS.get_datetime() dictionary.
static func make_run_id(character_id, danger, dt):
	var ch = str(character_id)
	if ch.begins_with("character_"):
		ch = ch.substr(len("character_"))
	return "%04d%02d%02d-%02d%02d%02d-%s-d%d" % [
		int(dt.year), int(dt.month), int(dt.day),
		int(dt.hour), int(dt.minute), int(dt.second), ch, int(danger)]
