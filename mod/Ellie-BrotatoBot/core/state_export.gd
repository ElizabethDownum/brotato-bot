extends Reference
# One JSON snapshot of the run for the decision client and the F9 "advise me"
# hotkey: the run, the build, and whatever shop or level-up options are on
# screen. No class_name -- callers preload this script.
#
#   serialize(parts, meta)   pure: reshapes plain Dictionaries/Arrays into the
#                            schema below (tested headlessly with a fixture)
#   file_name(run_id, seq, clock)  "<run_id>-<seq:03>.json"; with no open run
#                            (run_id "norun") "norun-<YYYYMMDD-HHMMSS>-<seq:03>.json"
#                            so exports from different sessions never collide
#   write(dir, run_id, seq, data, clock)  writes <dir>/<file_name>, returns the path
#   effective_plan_id(loaded, character_id)  the plan in effect: the plan file's
#                            plan_id when it is for this character, else "builtin"
#                            ("" on failure, with a push_warning)
#   collect(player_index)    game side: builds `parts` from RunData, the player
#                            node, the shop / level-up UI on screen, the plan
#                            file and BotRuntime. Never throws: anything missing
#                            degrades to a push_warning and an empty section.
#
# collect reaches every game global through /root (RunData, Keys, Main,
# BotRuntime) and loads shop_advisor.gd at call time, so this file parses in the
# headless test project, which has none of the game's classes or autoloads.
#
# Output (schema_version 1), keys in this order:
#   schema_version, kind, run_id, seq, exported_at (local ISO-8601, no offset),
#   wave, danger, character_id, hp, max_hp, gold (int or null),
#   stats {stat_*: float}, weapons [{id, tier, type, set_ids}],
#   items [{id, tier, count}] (copies grouped by id, first-seen order),
#   shop [{index, id, kind, tier, price, advisor_score, locked}] or [],
#   levelup_options [{index, stat, value, advisor_score}] or [],
#   unlocks_this_run [challenge_id], recent (last 10 snapshot dicts),
#   plan_id, target_challenge

const BotPaths = preload("bot_paths.gd")
const PlanFile = preload("plan_file.gd")
const DecisionClient = preload("decision_client.gd")

const SCHEMA_VERSION = 1
const NORUN_ID = "norun"
const BUILTIN_PLAN_ID = "builtin"
const RECENT_MAX = 10
const STATE_DIR = BotPaths.ROOT + "/state"
const SHOP_ADVISOR_PATH = "res://mods-unpacked/Ellie-BrotatoBot/shopping/shop_advisor.gd"

# WeaponData.Type.RANGED (items/global/weapon_data.gd:4, enum Type { MELEE, RANGED }).
const WEAPON_TYPE_RANGED = 1


# --- Pure -----------------------------------------------------------------------

# parts: the collect() dictionary (or a fixture). meta: {kind, run_id, seq,
# clock} where clock is an OS.get_datetime() dictionary. Shop and level-up
# entries take their "index" from the part when present (the on-screen slot),
# else their position in the list.
static func serialize(parts, meta):
	var out = {}
	out["schema_version"] = SCHEMA_VERSION
	out["kind"] = _str(meta.get("kind"))
	out["run_id"] = _str(meta.get("run_id"))
	out["seq"] = int(meta.get("seq", 0))
	out["exported_at"] = iso8601(meta.get("clock", {}))
	out["wave"] = _int_or_null(parts.get("wave"))
	out["danger"] = _int_or_null(parts.get("danger"))
	out["character_id"] = _str(parts.get("character_id"))
	out["hp"] = _int_or_null(parts.get("hp"))
	out["max_hp"] = _int_or_null(parts.get("max_hp"))
	out["gold"] = _int_or_null(parts.get("gold"))

	var stats = {}
	var in_stats = parts.get("stats")
	if typeof(in_stats) == TYPE_DICTIONARY:
		for k in in_stats.keys():
			stats[str(k)] = float(in_stats[k])
	out["stats"] = stats

	var weapons = []
	for w in _array(parts.get("weapons")):
		if typeof(w) != TYPE_DICTIONARY:
			continue
		var set_ids = []
		for s in _array(w.get("set_ids")):
			set_ids.append(str(s))
		weapons.append({"id": _str(w.get("id")), "tier": int(w.get("tier", 0)),
				"type": _str(w.get("type")), "set_ids": set_ids})
	out["weapons"] = weapons

	var items = []
	var item_at = {}
	for it in _array(parts.get("items")):
		if typeof(it) != TYPE_DICTIONARY:
			continue
		var id = _str(it.get("id"))
		if item_at.has(id):
			items[item_at[id]]["count"] += 1
		else:
			item_at[id] = items.size()
			items.append({"id": id, "tier": int(it.get("tier", 0)), "count": 1})
	out["items"] = items

	var shop = []
	var shop_in = _array(parts.get("shop"))
	for i in range(shop_in.size()):
		var e = shop_in[i]
		if typeof(e) != TYPE_DICTIONARY:
			continue
		shop.append({"index": int(e.get("index", i)), "id": _str(e.get("id")),
				"kind": _str(e.get("kind")), "tier": int(e.get("tier", 0)),
				"price": int(e.get("price", 0)), "advisor_score": float(e.get("advisor_score", 0.0)),
				"locked": bool(e.get("locked", false))})
	out["shop"] = shop

	var levelup = []
	var lv_in = _array(parts.get("levelup_options"))
	for i in range(lv_in.size()):
		var o = lv_in[i]
		if typeof(o) != TYPE_DICTIONARY:
			continue
		levelup.append({"index": int(o.get("index", i)), "stat": _str(o.get("stat")),
				"value": int(o.get("value", 0)), "advisor_score": float(o.get("advisor_score", 0.0))})
	out["levelup_options"] = levelup

	var unlocks = []
	for u in _array(parts.get("unlocks_this_run")):
		unlocks.append(str(u))
	out["unlocks_this_run"] = unlocks

	var recent_in = _array(parts.get("recent"))
	var recent = []
	for i in range(max(0, recent_in.size() - RECENT_MAX), recent_in.size()):
		var r = recent_in[i]
		recent.append(r.duplicate(true) if typeof(r) == TYPE_DICTIONARY else r)
	out["recent"] = recent

	out["plan_id"] = _str(parts.get("plan_id"))
	out["target_challenge"] = _str(parts.get("target_challenge"))
	return out


# OS.get_datetime() dictionary -> "YYYY-MM-DDTHH:MM:SS" (local time). "" when empty.
static func iso8601(dt):
	if typeof(dt) != TYPE_DICTIONARY or not dt.has("year"):
		return ""
	return "%04d-%02d-%02dT%02d:%02d:%02d" % [int(dt.year), int(dt.month), int(dt.day),
			int(dt.get("hour", 0)), int(dt.get("minute", 0)), int(dt.get("second", 0))]


# OS.get_datetime() dictionary -> "YYYYMMDD-HHMMSS" (as RunRecorder.make_run_id).
static func stamp(dt):
	if typeof(dt) != TYPE_DICTIONARY or not dt.has("year"):
		return "00000000-000000"
	return "%04d%02d%02d-%02d%02d%02d" % [int(dt.year), int(dt.month), int(dt.day),
			int(dt.get("hour", 0)), int(dt.get("minute", 0)), int(dt.get("second", 0))]


# The export's id: file_name without ".json" (also the decision request id).
static func export_id(run_id, seq, clock = {}):
	return file_name(run_id, seq, clock).get_basename()


# clock is the OS.get_datetime() dictionary serialize() received.
static func file_name(run_id, seq, clock = {}):
	if str(run_id) == NORUN_ID:
		return "%s-%s-%03d.json" % [NORUN_ID, stamp(clock), int(seq)]
	return "%s-%03d.json" % [str(run_id), int(seq)]


# Mirrors main.gd's run header and PlanFile.apply: a plan file applies only to
# the character it names.
static func effective_plan_id(loaded, character_id):
	if typeof(loaded) == TYPE_DICTIONARY and str(character_id) != "" \
			and str(loaded.get("character_id", "")) == str(character_id):
		return str(loaded.get("plan_id", ""))
	return BUILTIN_PLAN_ID


# Writes data as pretty JSON to <dir>/<file_name(run_id, seq, clock)>, creating
# dir, atomically (DecisionClient.write_atomic: <path>.tmp, then rename), so an
# F9 watcher never reads a half-written file. Returns the path, or "" (with a
# push_warning) when it cannot be written.
static func write(dir_path, run_id, seq, data, clock = {}):
	var d = Directory.new()
	if not d.dir_exists(dir_path) and d.make_dir_recursive(dir_path) != OK:
		push_warning("StateExport: cannot create %s" % dir_path)
		return ""
	var path = str(dir_path).plus_file(file_name(run_id, seq, clock))
	if DecisionClient.write_atomic(path, JSON.print(data, "  ")) != OK:
		return ""
	return path


static func _str(v):
	return "" if v == null else str(v)


static func _int_or_null(v):
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_REAL:
		return int(v)
	return null


static func _array(v):
	if typeof(v) == TYPE_ARRAY:
		return v
	return []


# --- Game side ------------------------------------------------------------------

# Builds the parts dictionary for serialize() from the live game. Read-only:
# it never buys, picks, steers or changes bot state.
static func collect(player_index):
	var p = int(player_index)
	var parts = {}
	var tree = Engine.get_main_loop()
	if tree == null or not (tree is SceneTree):
		push_warning("StateExport: no SceneTree")
		return parts
	var root = tree.root

	# Plan, target and recent snapshots do not need a run.
	var loaded = PlanFile.load_cached(PlanFile.DEFAULT_PATH)
	parts["plan_id"] = BUILTIN_PLAN_ID   # replaced once the character is known
	# Path lookup, not BotRuntime.instance(): preloading bot_runtime.gd here would
	# be a preload cycle, and this file must parse in the headless test project.
	var rt = root.get_node_or_null("BotRuntime")
	var config = rt.config if rt != null and typeof(rt.config) == TYPE_DICTIONARY else {}
	parts["target_challenge"] = PlanFile.target_id(loaded, config)
	if rt != null and "recent_snapshots" in rt:
		parts["recent"] = rt.recent_snapshots.duplicate(true)

	var rd = root.get_node_or_null("RunData")
	if rd == null:
		push_warning("StateExport: /root/RunData missing; run sections empty")
		return parts
	parts["wave"] = rd.current_wave
	parts["danger"] = rd.current_difficulty
	parts["unlocks_this_run"] = _unlock_ids(rd.challenges_completed_this_run, root)
	if p < 0 or p >= rd.get_player_count():
		push_warning("StateExport: no player %d in RunData; player sections empty" % p)
		return parts

	var character = rd.get_player_character(p)
	var character_id = character.my_id if character != null else ""
	parts["character_id"] = character_id
	parts["plan_id"] = effective_plan_id(loaded, character_id)
	parts["gold"] = rd.get_player_gold(p)
	parts["stats"] = _stats(rd, root, p)
	parts["weapons"] = _weapons(rd.get_player_weapons(p))
	parts["items"] = _items(rd.get_player_items(p))

	var main = root.get_node_or_null("Main")
	if main != null and "_players" in main and p < main._players.size():
		var player = main._players[p]
		if player != null and is_instance_valid(player):
			parts["hp"] = player.current_stats.health
			parts["max_hp"] = player.max_stats.health

	var advisor = load(SHOP_ADVISOR_PATH)
	var plan = advisor.get_plan(character_id) if advisor != null else null
	parts["shop"] = _shop(tree.current_scene, advisor, plan, p)
	parts["levelup_options"] = _levelup(main, rd, advisor, plan, p)
	return parts


# stat_* entries of RunData.get_player_effects(p) (keys are Keys hashes), valued
# with RunData.get_stat (effect times its gain_ modifier, as ShopAdvisor reads).
static func _stats(rd, root, p):
	var out = {}
	var keys = root.get_node_or_null("Keys")
	if keys == null:
		push_warning("StateExport: /root/Keys missing; stats empty")
		return out
	var effects = rd.get_player_effects(p)
	if typeof(effects) != TYPE_DICTIONARY:
		return out
	for k in effects.keys():
		var sname = keys.hash_to_string.get(k, "") if typeof(k) == TYPE_INT else str(k)
		if not sname.begins_with("stat_"):
			continue
		var v = effects[k]
		if typeof(v) != TYPE_INT and typeof(v) != TYPE_REAL:
			continue
		out[sname] = float(rd.get_stat(k, p)) if typeof(k) == TYPE_INT else float(v)
	return out


static func _weapons(list):
	var out = []
	for w in list:
		if w == null:
			continue
		var set_ids = []
		if w.sets != null:
			for s in w.sets:
				if s != null:
					set_ids.append(s.my_id)
		out.append({"id": w.my_id, "tier": w.tier,
				"type": "ranged" if w.type == WEAPON_TYPE_RANGED else "melee", "set_ids": set_ids})
	return out


# One entry per copy; serialize() groups them into counts.
static func _items(list):
	var out = []
	for it in list:
		if it != null:
			out.append({"id": it.my_id, "tier": it.tier})
	return out


# ChallengeData resources (my_id); a loaded save may hold hashes instead.
static func _unlock_ids(list, root):
	var out = []
	if typeof(list) != TYPE_ARRAY:
		return out
	var keys = root.get_node_or_null("Keys")
	for c in list:
		if c == null:
			continue
		if typeof(c) == TYPE_OBJECT and "my_id" in c:
			out.append(c.my_id)
		elif typeof(c) == TYPE_INT and keys != null:
			out.append(keys.hash_to_string.get(c, str(c)))
		else:
			out.append(str(c))
	return out


# The shop on screen: the current scene is a BaseShop (shop.gd / coop_shop.gd)
# exposing _get_shop_items_container(p). Bought slots (active == false) are left
# out; index is the slot position in _shop_items.
static func _shop(scene, advisor, plan, p):
	var out = []
	if scene == null or not scene.has_method("_get_shop_items_container"):
		return out
	var container = scene._get_shop_items_container(p)
	if container == null or not is_instance_valid(container) or not ("_shop_items" in container):
		push_warning("StateExport: shop has no items container for player %d" % p)
		return out
	var nodes = container._shop_items
	for i in range(nodes.size()):
		var node = nodes[i]
		if node == null or not is_instance_valid(node) or not node.active or node.item_data == null:
			continue
		var data = node.item_data
		var score = 0.0
		if advisor != null and plan != null:
			score = advisor.score_shop_entry([data, node.wave_value], plan, p)
		out.append({"index": i, "id": data.my_id, "kind": "weapon" if "weapon_id" in data else "item",
				"tier": data.tier, "price": node.value, "advisor_score": score, "locked": node.locked})
	return out


# The level-up choices on screen for player p: Main's UpgradesUI (solo) or
# CoopUpgradesUI (co-op), shown, with p still choosing and the upgrade list (not
# a crate item) visible. The score is ShopAdvisor.stat_score over the option's
# effects -- the same per-option score pick_upgrade maximises.
static func _levelup(main, rd, advisor, plan, p):
	var out = []
	if main == null:
		return out
	var ui = main.get("_coop_upgrades_ui") if rd.is_coop_run else main.get("_upgrades_ui")
	if ui == null or not is_instance_valid(ui) or not ui.visible:
		return out
	var choosing = ui.get("_player_is_choosing")
	if typeof(choosing) != TYPE_ARRAY or p >= choosing.size() or not choosing[p]:
		return out
	var container = ui._get_player_container(p)
	if container == null or not container._upgrades_container.visible:
		return out
	var ups = container._old_upgrades
	if typeof(ups) != TYPE_ARRAY:
		return out
	for i in range(ups.size()):
		var u = ups[i]
		if u == null or u.effects == null or u.effects.empty():
			continue
		var e = u.effects[0]
		var score = 0.0
		if advisor != null and plan != null:
			score = advisor.stat_score(u.effects, plan, p)
		out.append({"index": i, "stat": e.key, "value": e.value, "advisor_score": score})
	return out
