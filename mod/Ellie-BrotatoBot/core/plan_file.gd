extends Reference
# Per-run build plan read from user://brotato-bot/plan.json. Pure logic: every
# function takes an explicit path so it runs in the headless test project.
# No class_name -- callers preload this script (see shopping/build_plans.gd).
#
# File shape:
#   {"plan_id": str, "character_id": str, "target_challenge": str (optional),
#    "plan": {...BOTato plan keys, see build_plans.gd DEFAULT...}}
#
# load_from(path) returns that dictionary (target_challenge defaulted to "") or
# null when the file is missing, unreadable, invalid JSON, not an object, or
# lacks plan_id / character_id / plan. Reasons are logged with push_warning.
# Other top-level keys (the harness's "danger" and "starting_weapon") are left
# untouched and ignored here; the launcher reads them from launch.json instead.

# Relative preload: resolves in the game (res://mods-unpacked/...) and in the
# headless test project (res://mod/...) alike.
const BotPaths = preload("bot_paths.gd")

const DEFAULT_PATH = BotPaths.ROOT + "/plan.json"

# Keys merged one level deep by merge(); every other key is replaced wholesale.
const DEEP_KEYS = ["stats", "item_bonus", "prefer_sets", "steering"]

const STEERING_TYPES = {
	"tree_value": "number", "sweep": "number", "sweep_radius": "number",
	"gold_value": "number", "stand_continuity": "number", "tree_policy": "tree_policy",
}

# BOTato plan keys whose built-in values are ints. JSON numbers parse as floats,
# so load_from converts these back with int() (e.g. for range()/%d use).
const INT_PLAN_KEYS = ["harvest_cap", "max_weapons", "reroll_keep", "max_rerolls", "gold_floor"]

# The plan keys the shop and level-up code read, with the type each is read as
# (the sidecar's schema.PlanPatch is the same table). apply_patch drops every
# other key and every wrong-typed value, so a bad response cannot corrupt
# plan.json. JSON numbers parse as floats, so INT_PLAN_KEYS are "integer":
# a whole-number float such as 4.0 passes, 2.5 does not (load_from truncates).
const KEY_TYPES = {
	"weapon_type": "weapon_type", "weapon_set": "string",
	"stats": "number_map", "item_bonus": "number_map", "prefer_sets": "number_map",
	"phase_boost": "phase_boost",
	"steering": "steering",
	"harvest_cap": "integer", "max_weapons": "integer", "reroll_keep": "integer",
	"max_rerolls": "integer", "gold_floor": "integer", "min_buy": "number",
	"prefer_weapons": "string_list", "ban_items": "string_list",
	"deprioritize_weapons": "string_list", "ask_on": "string_list",
	"unique_weapons": "bool", "stack_combine": "bool", "hitrate_pref": "bool",
	"spend_surplus": "bool",
}

# mtime cache for load_cached(): path -> {"mtime": int, "data": Dictionary|null}.
# Godot 3 has no static vars; a const Dictionary is shared by all users of the
# script and stays mutable, so it serves as the cache holder.
const _CACHE = {}


static func mtime(path):
	var f = File.new()
	if not f.file_exists(path):
		return 0
	return f.get_modified_time(path)


static func load_from(path):
	var f = File.new()
	if not f.file_exists(path):
		return null
	if f.open(path, File.READ) != OK:
		push_warning("PlanFile: cannot open %s" % path)
		return null
	var text = f.get_as_text()
	f.close()
	var parsed = JSON.parse(text)
	if parsed.error != OK:
		push_warning("PlanFile: invalid JSON in %s (line %d: %s)"
			% [path, parsed.error_line, parsed.error_string])
		return null
	var d = parsed.result
	if typeof(d) != TYPE_DICTIONARY:
		push_warning("PlanFile: %s is not a JSON object" % path)
		return null
	for k in ["plan_id", "character_id", "plan"]:
		if not d.has(k):
			push_warning("PlanFile: %s lacks required key '%s'" % [path, k])
			return null
	if typeof(d.plan) != TYPE_DICTIONARY:
		push_warning("PlanFile: %s 'plan' is not an object" % path)
		return null
	d.plan_id = str(d.plan_id)
	d.character_id = str(d.character_id)
	if not d.has("target_challenge") or d.target_challenge == null:
		d.target_challenge = ""
	d.target_challenge = str(d.target_challenge)
	_normalize_ints(d.plan)
	if d.plan.has("steering"):
		d.plan.steering = valid_steering(d.plan.steering)
	return d


# load_from(path), re-reading the file only when its mtime changes. Returns the
# cached result (possibly null). Call it wherever a changed file should be seen.
static func load_cached(path):
	var m = mtime(path)
	if m == 0:
		_CACHE.erase(path)
		return null
	if _CACHE.has(path) and _CACHE[path].mtime == m:
		return _CACHE[path].data
	var data = load_from(path)
	_CACHE[path] = {"mtime": m, "data": data}
	return data


# Writes plan (the file shape above) to path as indented JSON: <path>.tmp, then
# renamed over path (an existing file is removed first; Godot 3's rename does
# not replace on every platform). Drops the load_cached entry for path, since a
# rewrite within the same second can keep the 1 s mtime unchanged. Returns OK
# or the failing error code (with a push_warning).
static func save(path, plan) -> int:
	_CACHE.erase(path)
	var d = Directory.new()
	var dir_path = str(path).get_base_dir()
	if not d.dir_exists(dir_path) and d.make_dir_recursive(dir_path) != OK:
		push_warning("PlanFile: cannot create %s" % dir_path)
		return ERR_CANT_CREATE
	var tmp = path + ".tmp"
	var f = File.new()
	var err = f.open(tmp, File.WRITE)
	if err != OK:
		push_warning("PlanFile: cannot open %s (error %d)" % [tmp, err])
		return err
	f.store_string(JSON.print(plan, "  "))
	f.close()
	if d.file_exists(path):
		d.remove(path)
	err = d.rename(tmp, path)
	if err != OK:
		push_warning("PlanFile: cannot rename %s (error %d)" % [tmp, err])
		d.remove(tmp)
	return err


# Merges patch (plan keys, as in a revise_plan response) into the plan file at
# path for character_id and saves it. Keys that fail value_ok are dropped (with a
# push_warning) before the merge. A missing file is created as
# {plan_id: new_plan_id, character_id, target_challenge: "", plan: patch}.
# Refuses (returns ERR_UNAVAILABLE, with a push_warning) rather than overwrite
# a file that exists but does not load, or one written for another character.
# Returns OK or the save error.
static func apply_patch(path, character_id, patch, new_plan_id) -> int:
	var loaded = load_from(path)
	if loaded == null:
		if File.new().file_exists(path):
			push_warning("PlanFile: %s exists but does not load; patch not applied" % path)
			return ERR_UNAVAILABLE
		loaded = {"plan_id": str(new_plan_id), "character_id": str(character_id),
			"target_challenge": "", "plan": {}}
	elif loaded.character_id != str(character_id):
		push_warning("PlanFile: %s is for %s, not %s; patch not applied"
			% [path, loaded.character_id, str(character_id)])
		return ERR_UNAVAILABLE
	var typed = {}
	for k in patch.keys():
		if value_ok(k, patch[k]):
			typed[k] = patch[k]
		else:
			push_warning("PlanFile: plan_patch key '%s' is unknown or wrong-typed; dropped" % str(k))
	loaded.plan = merge(loaded.plan, typed)
	return save(path, loaded)


# True when key is in KEY_TYPES and v has that type.
static func value_ok(key, v) -> bool:
	return _type_ok(KEY_TYPES.get(key, ""), v)


# Keep usable siblings from a hand-written plan; warn once when the file loads.
static func valid_steering(v) -> Dictionary:
	var out = {}
	if typeof(v) != TYPE_DICTIONARY:
		push_warning("PlanFile: steering is not an object; ignored")
		return out
	for k in v:
		if _type_ok(STEERING_TYPES.get(k, ""), v[k]):
			out[k] = v[k]
		else:
			push_warning("PlanFile: steering key '%s' is unknown or wrong-typed; ignored" % str(k))
	return out


static func _type_ok(kind, v) -> bool:
	match kind:
		"number":
			return typeof(v) == TYPE_REAL or typeof(v) == TYPE_INT
		"integer":
			return typeof(v) == TYPE_INT or (typeof(v) == TYPE_REAL and v == floor(v))
		"string":
			return typeof(v) == TYPE_STRING
		"bool":
			return typeof(v) == TYPE_BOOL
		"weapon_type":
			return typeof(v) == TYPE_STRING and v in ["ranged", "melee", "any"]
		"tree_policy":
			return typeof(v) == TYPE_STRING and v in ["auto", "seek", "preserve"]
		"steering":
			if typeof(v) != TYPE_DICTIONARY:
				return false
			for k in v:
				if not _type_ok(STEERING_TYPES.get(k, ""), v[k]):
					return false
			return true
		"string_list":
			if typeof(v) != TYPE_ARRAY:
				return false
			for e in v:
				if typeof(e) != TYPE_STRING:
					return false
			return true
		"number_map":
			if typeof(v) != TYPE_DICTIONARY:
				return false
			for k in v.keys():
				if typeof(k) != TYPE_STRING or not _type_ok("number", v[k]):
					return false
			return true
		"phase_boost":
			if typeof(v) != TYPE_DICTIONARY:
				return false
			for k in v.keys():
				var sub_kind = {"until_wave": "integer", "stats": "number_map"}.get(k, "")
				if not _type_ok(sub_kind, v[k]):
					return false
			return true
	return false


# base.duplicate(true) overlaid with override: DEEP_KEYS merge one
# level deep when both sides are dictionaries; any other key replaces wholesale.
# Neither input is mutated and the result shares no containers with them.
static func merge(base, override):
	var out = base.duplicate(true)
	for k in override.keys():
		var v = override[k]
		if k in DEEP_KEYS and typeof(v) == TYPE_DICTIONARY and out.has(k) \
				and typeof(out[k]) == TYPE_DICTIONARY:
			for sk in v.keys():
				out[k][sk] = _copy(v[sk])
		else:
			out[k] = _copy(v)
	return out


# The plan to use for character_id: merge(built_in, loaded.plan) when a plan file
# was loaded and its character_id matches; otherwise built_in unchanged. A plan
# written for another character never applies.
static func apply(built_in, loaded, character_id):
	if typeof(loaded) == TYPE_DICTIONARY and loaded.character_id == str(character_id):
		return merge(built_in, loaded.plan)
	return built_in


# The plan for character_id given the plan file at path: apply() over the
# mtime-cached load. BuildPlans.get_plan calls this with DEFAULT_PATH on every
# call, so a rewritten file is seen at the next shop or level-up decision.
static func plan_for(built_in, character_id, path):
	return apply(built_in, load_cached(path), character_id)


# The challenge id the mod targets: the plan file's target_challenge when
# non-empty, else the config's.
static func target_id(loaded, config):
	if typeof(loaded) == TYPE_DICTIONARY and str(loaded.get("target_challenge", "")) != "":
		return str(loaded.target_challenge)
	return str(config.get("target_challenge", ""))


static func _copy(v):
	if typeof(v) == TYPE_DICTIONARY or typeof(v) == TYPE_ARRAY:
		return v.duplicate(true)
	return v


static func _normalize_ints(plan):
	for k in INT_PLAN_KEYS:
		if plan.has(k) and typeof(plan[k]) == TYPE_REAL:
			plan[k] = int(plan[k])
	if plan.has("phase_boost") and typeof(plan.phase_boost) == TYPE_DICTIONARY \
			and plan.phase_boost.has("until_wave") and typeof(plan.phase_boost.until_wave) == TYPE_REAL:
		plan.phase_boost.until_wave = int(plan.phase_boost.until_wave)
