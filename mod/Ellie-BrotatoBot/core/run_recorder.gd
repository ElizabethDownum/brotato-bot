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
# Animated cleanup cannot supply bag_after until the next wave's first frame.
var _pending_wave_end = null


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
	finish_wave_end()
	event("end", outcome)
	_close()


func _close():
	finish_wave_end()
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


# A checkpoint may precede its delayed wave_end: carry the wave at write time.
static func checkpoint_event(wave, data: Dictionary) -> Dictionary:
	var out = data.duplicate(true)
	out["wave"] = int(wave)
	return out


# One offer event (the board the shop showed): view is 1-based per visit (a reroll
# starts the next view); items are offer_item() entries.
static func offer_event(wave, view, gold, items) -> Dictionary:
	return {"wave": int(wave), "view": int(view), "gold": int(gold), "items": items}


static func offer_item(id, tier, price, score, locked) -> Dictionary:
	return {"id": str(id), "tier": int(tier), "price": int(price), "score": float(score),
		"locked": bool(locked)}


# A crate item the level-up screen took or recycled (action "take" | "recycle").
# source: haiku/rule/timeout; id links the decision, or is empty when not asked.
static func crate_event(wave, item_id, action, score, source = "rule", decision_id = "") -> Dictionary:
	return {"wave": int(wave), "item_id": str(item_id), "action": str(action), "score": float(score),
		"source": str(source), "id": str(decision_id)}


# The run's final build: weapon and item ids.
static func build_event(weapons, items) -> Dictionary:
	return {"weapons": weapons, "items": items}


# The snapshot's mats block. Each pickup is {position: Vector2, value: int,
# unattached: bool}; floor and nearest include already-attracted pickups too.
static func mats(pickups: Array, origin: Vector2, bag) -> Dictionary:
	var nearest = -1
	var floor_value = 0
	var unattached = 0
	for p in pickups:
		var d = int(origin.distance_to(p.position))
		if nearest < 0 or d < nearest:
			nearest = d
		floor_value += int(p.value)
		if p.unattached:
			unattached += 1
	return {"floor": pickups.size(), "floor_value": floor_value, "unattached": unattached,
		"bag": int(bag), "nearest": nearest}


static func wave_materials(floor_count, floor_value, bag_before, bag_after,
		gold_at_end = null, gold_at_start = null) -> Dictionary:
	return {"floor_count": int(floor_count), "floor_value": int(floor_value),
		"bag_before": int(bag_before), "bag_after": null if bag_after == null else int(bag_after),
		"collected_value": null if gold_at_end == null or gold_at_start == null \
			else int(gold_at_end - gold_at_start)}


static func wave_trees(spawned, felled, alive) -> Dictionary:
	return {"spawned": int(spawned), "felled": int(felled), "alive": int(alive)}


# Capture all pre-cleanup fields now; emit when the outgoing bag is observed.
# Finish a previous pending wave as unknown rather than silently replacing it.
func begin_wave_end(data: Dictionary):
	finish_wave_end()
	_pending_wave_end = data.duplicate(true)


# Called after optimized cleanup or before the next wave can spawn materials.
# If the run closes first, null explicitly means the bag was not observed.
func finish_wave_end(bag_after = null):
	if _pending_wave_end == null:
		return
	_pending_wave_end.materials.bag_after = null if bag_after == null else int(bag_after)
	event("wave_end", _pending_wave_end)
	_pending_wave_end = null


# The launch event (spec: the launcher consumed launch.json): which launch the
# run came from, so the harness can tie the run to the plan's token.
static func launch_event(launch) -> Dictionary:
	return {
		"token": str(launch.get("token", "")),
		"character_id": str(launch.get("character_id", "")),
		"starting_weapon": str(launch.get("starting_weapon", "")),
		"danger": int(launch.get("danger", 0)),
		"zone": int(launch.get("zone", 0)),
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
