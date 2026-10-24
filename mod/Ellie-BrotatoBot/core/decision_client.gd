extends Reference
# File-based decision protocol between the mod and the sidecar (spec 7.4). No
# network, no input injection: the mod writes a request file, the sidecar
# writes a response file, the mod polls for it. Pure file logic; the pause /
# poll loop lives in BotRuntime.decide. No class_name -- callers preload this
# script.
#
# Files under root (BotPaths.ROOT in the game):
#   requests/<id>.json   {id, kind, screen, run_id, seq, state_path, options,
#                        deadline_ms} (build_request plus id)
#                        kind: "shop" | "levelup" | "crate" | "pivot" | "checkpoint";
#                        screen: "shop" | "levelup" | "crate" | "checkpoint" (which
#                        screen asks: a pivot comes from the shop or a level-up);
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

const ACTIONS = ["buy", "reroll", "lock", "pass", "skip", "pick", "take", "recycle", "revise_plan"]
const INDEX_ACTIONS = ["buy", "lock", "pass", "pick"]
const DEFAULT_TIE_MARGIN = 3.0
const DEFAULT_FLOOR = 6.0
const DEFAULT_GOLD_FLOOR = 200
const DEFAULT_BIG_SHARE = 0.25
const DEFAULT_PER_VISIT = 2
const ALIVE_FILE = "sidecar.alive"
const ALIVE_MAX_AGE_S = 10
const SCREENS = ["shop", "levelup", "crate", "checkpoint"]

var root_dir = BotPaths.ROOT


# ItemData inherits ItemParentData.effects (Array of Effect resources); Effect
# exports text_key. Also accepts dictionaries for headless tests. This detects
# description effects, independently of the plan's weights or the score.
static func has_description_effect(effects) -> bool:
	for effect in effects:
		if effect != null and "text_key" in effect and str(effect.text_key) != "":
			return true
	return false


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


# Whether to ask the sidecar, and why. scores: one number per option, parallel to
# offered_ids. affordable: indices into scores the player can pay for (all of
# them for level-ups). Missing cfg keys use the defaults.
#
# Level-up (min_buy null):
#   "pivot"  an offered id is in the plan's ask_on list (always asks)
#   "ask"    at least two options and the best is within ask_tie_margin of the
#            second, or below ask_floor
# Shop (min_buy given; gold, prices parallel to scores, asked_this_visit asks so
# far this visit), checked in this order:
#   ""       asked_this_visit has reached ask_per_visit
#   ""       a dead board: no affordable option scores at or above min_buy
#            (even with an ask_on id offered: an unaffordable goal never asks)
#   "pivot"  an offered id is in ask_on (on every board of the visit)
#   "ask"    a tie: best >= ask_floor and best - second < ask_tie_margin
#   "ask"    a big purchase: gold >= ask_gold_floor and the best affordable
#            option costs at least ask_big_share of gold (it cannot be an ask_on
#            id: any ask_on id on the board already pivoted)
#   ""       let the rules decide
static func should_ask(scores: Array, affordable: Array, cfg: Dictionary,
		offered_ids: Array = [], ask_on: Array = [], min_buy = null, gold: int = 0,
		prices: Array = [], asked_this_visit: int = 0) -> String:
	var shop = min_buy != null
	if shop and asked_this_visit >= int(cfg.get("ask_per_visit", DEFAULT_PER_VISIT)):
		return ""
	var vals = []
	var best_i = -1
	for i in affordable:
		var k = int(i)
		if k < 0 or k >= scores.size():
			continue
		vals.append(float(scores[k]))
		if best_i < 0 or float(scores[k]) > float(scores[best_i]):
			best_i = k
	var margin = float(cfg.get("ask_tie_margin", DEFAULT_TIE_MARGIN))
	var floor_v = float(cfg.get("ask_floor", DEFAULT_FLOOR))
	vals.sort()
	if shop and (best_i < 0 or float(scores[best_i]) < float(min_buy)):
		return ""
	for id in offered_ids:
		if ask_on.has(id):
			return "pivot"
	if not shop:
		if vals.size() < 2:
			return ""
		var top = vals[vals.size() - 1]
		if top - vals[vals.size() - 2] < margin or top < floor_v:
			return "ask"
		return ""
	var best = vals[vals.size() - 1]
	if vals.size() >= 2 and best >= floor_v and best - vals[vals.size() - 2] < margin:
		return "ask"
	if best_i < prices.size() \
			and gold >= int(cfg.get("ask_gold_floor", DEFAULT_GOLD_FLOOR)) \
			and float(prices[best_i]) >= float(cfg.get("ask_big_share", DEFAULT_BIG_SHARE)) * float(gold):
		return "ask"
	return ""


# The request body (write_request adds "id"). option_index in a response
# indexes options[] only, never the state file's shop[].index.
static func build_request(kind, screen, run_id, seq, state_path, options, deadline_ms) -> Dictionary:
	return {
		"kind": str(kind),
		"screen": str(screen),
		"run_id": str(run_id),
		"seq": int(seq),
		"state_path": str(state_path),
		"options": options,
		"deadline_ms": deadline_ms,
	}


# Writes requests/<id>.json atomically (tmp file, then rename) and returns the
# id, or "" (with a push_warning) when it cannot be written. The written object
# is req plus "id". id is req.id when given (BotRuntime passes the state
# file's base name, StateExport.export_id, so a norun request and its state
# file share norun-<stamp>-NNN), else request_id(run_id, seq).
func write_request(req: Dictionary) -> String:
	var id = str(req.id) if req.get("id") != null else request_id(req.get("run_id", ""), req.get("seq", 0))
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
#   option_index  int >= 0, required for buy / lock / pass / pick
#   confidence    number in 0..1
#   rationale     String when present
#   plan_patch    Dictionary, required for revise_plan
static func validate_response(r) -> bool:
	if typeof(r) != TYPE_DICTIONARY:
		return false
	if typeof(r.get("action")) != TYPE_STRING or not ACTIONS.has(r.action):
		return false
	if r.action in ["take", "recycle"] and r.has("option_index"):
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
