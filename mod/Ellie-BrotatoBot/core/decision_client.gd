extends Reference
# File-based decision protocol between the mod and the sidecar (spec 7.4). No
# network, no input injection: the mod writes a request file, the sidecar
# writes a response file, the mod polls for it. Pure file logic; the pause /
# poll loop lives in BotRuntime.decide. No class_name -- callers preload this
# script.
#
# Files under root (BotPaths.ROOT in the game):
#   requests/<id>.json   {id, kind, run_id, seq, state_path, options, deadline_ms}
#                        kind: "shop" | "levelup" | "pivot" | "checkpoint";
#                        id = "<run_id>-<seq:03>" (seq is the state export's,
#                        so state/<id>.json is the matching state file);
#                        deadline_ms is absolute epoch ms (OS.get_system_time_msecs)
#   responses/<id>.json  {action, option_index?, plan_patch?, confidence,
#                        rationale?, tags?} -- see validate_response
#
#   sidecar.alive        touched by the sidecar while it runs; the mod asks only
#                        while its mtime is fresh (sidecar_alive), so without
#                        a sidecar the rules decide with no request and no pause
#
# Requests are written to <id>.json.tmp and renamed, so the sidecar never reads
# a half-written file. Responses are read once and deleted; responses for any
# other id are stale (an earlier decision timed out) and deleted unread.

# Relative preload: resolves in the game (res://mods-unpacked/...) and in the
# headless test project (res://mod/...) alike.
const BotPaths = preload("bot_paths.gd")

const ACTIONS = ["buy", "reroll", "lock", "skip", "pick", "revise_plan"]
const INDEX_ACTIONS = ["buy", "lock", "pick"]
const DEFAULT_TIE_MARGIN = 3.0
const DEFAULT_FLOOR = 4.0
const ALIVE_FILE = "sidecar.alive"
const ALIVE_MAX_AGE_S = 10

var root_dir = BotPaths.ROOT


func _init(root = BotPaths.ROOT):
	root_dir = str(root)


func requests_dir() -> String:
	return root_dir.plus_file("requests")


func responses_dir() -> String:
	return root_dir.plus_file("responses")


static func request_id(run_id, seq) -> String:
	return "%s-%03d" % [str(run_id), int(seq)]


# True when <root_dir>/sidecar.alive exists and its mtime (unix seconds) is at
# most max_age_s before now_unix (pass OS.get_unix_time()).
static func sidecar_alive(root_dir: String, now_unix: int, max_age_s: int = ALIVE_MAX_AGE_S) -> bool:
	var path = root_dir.plus_file(ALIVE_FILE)
	var f = File.new()
	if not f.file_exists(path):
		return false
	return now_unix - int(f.get_modified_time(path)) <= max_age_s


# Deletes responses/<id>.json if present, so a leftover answer from an earlier
# session that reused the id (e.g. a norun id) is not taken as this answer.
# Call before write_request.
func discard_response(id: String) -> void:
	var path = responses_dir().plus_file(id + ".json")
	var d = Directory.new()
	if d.file_exists(path):
		d.remove(path)


# Whether to ask the sidecar, and why:
#   "pivot"  some offered id is in the plan's ask_on list (always asks)
#   "ask"    at least two affordable options and the best affordable score is
#            within ask_tie_margin of the second, or below ask_floor
#   ""       let the rules decide
# scores: one number per option. affordable: indices into scores the player
# can pay for (all of them for level-ups). Missing cfg keys use the defaults.
static func should_ask(scores: Array, affordable: Array, cfg: Dictionary,
		offered_ids: Array = [], ask_on: Array = []) -> String:
	for id in offered_ids:
		if ask_on.has(id):
			return "pivot"
	var vals = []
	for i in affordable:
		var k = int(i)
		if k >= 0 and k < scores.size():
			vals.append(float(scores[k]))
	if vals.size() < 2:
		return ""
	vals.sort()
	var best = vals[vals.size() - 1]
	var second = vals[vals.size() - 2]
	var margin = float(cfg.get("ask_tie_margin", DEFAULT_TIE_MARGIN))
	var floor_v = float(cfg.get("ask_floor", DEFAULT_FLOOR))
	if best - second < margin or best < floor_v:
		return "ask"
	return ""


# Writes requests/<id>.json atomically (tmp file, then rename) and returns the
# id, or "" (with a push_warning) when it cannot be written. The written object
# is req plus "id".
func write_request(req: Dictionary) -> String:
	var id = request_id(req.get("run_id", ""), req.get("seq", 0))
	var dir_path = requests_dir()
	var d = Directory.new()
	if not d.dir_exists(dir_path) and d.make_dir_recursive(dir_path) != OK:
		push_warning("DecisionClient: cannot create %s" % dir_path)
		return ""
	var body = req.duplicate(true)
	body["id"] = id
	var path = dir_path.plus_file(id + ".json")
	if write_atomic(path, JSON.print(body, "  ")) != OK:
		return ""
	return id


# Writes text to path + ".tmp", then renames it over path (removing an existing
# path first: Godot 3's rename does not replace on every platform). Returns OK
# or the failing error code (with a push_warning).
static func write_atomic(path: String, text: String) -> int:
	var tmp = path + ".tmp"
	var f = File.new()
	var err = f.open(tmp, File.WRITE)
	if err != OK:
		push_warning("DecisionClient: cannot open %s (error %d)" % [tmp, err])
		return err
	f.store_string(text)
	f.close()
	var d = Directory.new()
	if d.file_exists(path):
		d.remove(path)
	err = d.rename(tmp, path)
	if err != OK:
		push_warning("DecisionClient: cannot rename %s (error %d)" % [tmp, err])
		d.remove(tmp)
	return err


# The response for id, read once and deleted; null when none has arrived.
# Every other *.json in responses/ is stale and deleted unread. A response file
# that is not a JSON object (parse error, array, ...) is still deleted and
# returned as {} so the caller treats it as invalid (validate_response({}) is
# false) instead of waiting for the timeout.
func poll_response(id):
	var dir_path = responses_dir()
	var d = Directory.new()
	if d.open(dir_path) != OK:
		return null
	var mine = ""
	var stale = []
	d.list_dir_begin(true, true)
	var f = d.get_next()
	while f != "":
		if not d.current_is_dir() and f.ends_with(".json"):
			if f == id + ".json":
				mine = f
			else:
				stale.append(f)
		f = d.get_next()
	d.list_dir_end()
	for s in stale:
		d.remove(dir_path.plus_file(s))
	if mine == "":
		return null
	var path = dir_path.plus_file(mine)
	var file = File.new()
	var text = ""
	if file.open(path, File.READ) == OK:
		text = file.get_as_text()
		file.close()
	d.remove(path)
	var parsed = JSON.parse(text)
	if parsed.error != OK or typeof(parsed.result) != TYPE_DICTIONARY:
		push_warning("DecisionClient: response %s is not a JSON object" % path)
		return {}
	return parsed.result


# True when r is a usable response. Normalizes r in place: a whole-number float
# option_index (JSON numbers parse as floats) becomes an int, and confidence
# becomes a float.
#   action        one of ACTIONS
#   option_index  int >= 0, required for buy / lock / pick
#   confidence    number in 0..1
#   rationale     String when present
#   plan_patch    Dictionary, required for revise_plan
static func validate_response(r) -> bool:
	if typeof(r) != TYPE_DICTIONARY:
		return false
	if typeof(r.get("action")) != TYPE_STRING or not ACTIONS.has(r.action):
		return false
	if INDEX_ACTIONS.has(r.action):
		var idx = r.get("option_index")
		if typeof(idx) == TYPE_REAL:
			if idx != floor(idx):
				return false
			idx = int(idx)
		if typeof(idx) != TYPE_INT or idx < 0:
			return false
		r["option_index"] = idx
	var c = r.get("confidence")
	if typeof(c) != TYPE_REAL and typeof(c) != TYPE_INT:
		return false
	c = float(c)
	if c < 0.0 or c > 1.0:
		return false
	r["confidence"] = c
	if r.has("rationale") and typeof(r.rationale) != TYPE_STRING:
		return false
	if r.action == "revise_plan" and typeof(r.get("plan_patch")) != TYPE_DICTIONARY:
		return false
	return true
