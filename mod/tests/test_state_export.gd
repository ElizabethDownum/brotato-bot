extends "res://mod/tests/test_base.gd"

const StateExport = preload("res://mod/Ellie-BrotatoBot/core/state_export.gd")

const FIXTURE = "res://mod/tests/fixtures/state_parts.json"

const KEYS = ["schema_version", "kind", "run_id", "seq", "exported_at", "wave", "danger",
		"character_id", "hp", "max_hp", "gold", "stats", "weapons", "items", "shop",
		"levelup_options", "unlocks_this_run", "recent", "plan_id", "target_challenge"]

const CLOCK = {"year": 2026, "month": 10, "day": 21, "hour": 9, "minute": 5, "second": 7,
		"weekday": 3, "dst": false}


func _parts():
	var f = File.new()
	if f.open(FIXTURE, File.READ) != OK:
		failures.append("cannot open %s" % FIXTURE)
		return {}
	var parsed = JSON.parse(f.get_as_text())
	f.close()
	if parsed.error != OK or typeof(parsed.result) != TYPE_DICTIONARY:
		failures.append("fixture is not a JSON object")
		return {}
	return parsed.result


func _meta():
	return {"kind": "advise", "run_id": "20261021-090000-well_rounded-d2", "seq": 3, "clock": CLOCK}


func test_serialize_shapes_output():
	var out = StateExport.serialize(_parts(), _meta())
	assert_eq(out.keys(), KEYS, "key list and order")
	assert_eq(out.get("schema_version"), 1, "schema_version")
	assert_eq(out.get("kind"), "advise", "kind")
	assert_eq(out.get("run_id"), "20261021-090000-well_rounded-d2", "run_id")
	assert_eq(out.get("seq"), 3, "seq")
	assert_eq(out.get("exported_at"), "2026-10-21T09:05:07", "exported_at from meta clock")
	assert_eq(out.get("wave"), 7, "wave is an int")
	assert_eq(out.get("danger"), 2, "danger")
	assert_eq(out.get("character_id"), "character_well_rounded", "character_id")
	assert_eq(out.get("hp"), 14, "hp")
	assert_eq(out.get("max_hp"), 22, "max_hp")
	assert_eq(out.get("gold"), 63, "gold")
	assert_eq(out.get("stats", {}).get("stat_ranged_damage"), 3.5, "stats copied")
	assert_eq(out.get("weapons", []).size(), 2, "two weapons")
	if out.get("weapons", []).size() == 2:
		var w = out.weapons[1]
		assert_eq(w.keys(), ["id", "tier", "type", "set_ids"], "weapon keys")
		assert_eq(w.get("id"), "weapon_knife_2", "weapon id")
		assert_eq(w.get("tier"), 1, "weapon tier int")
		assert_eq(w.get("set_ids"), ["set_precise", "set_blade"], "weapon set_ids")
	var items = out.get("items", [])
	assert_eq(items.size(), 3, "four copies of three items group to three entries")
	if items.size() == 3:
		assert_eq(items[0].keys(), ["id", "tier", "count"], "item keys")
		assert_eq(items[0].get("id"), "item_alien_eyes", "first-seen order")
		assert_eq(items[0].get("count"), 2, "duplicate counted")
		assert_eq(items[2].get("count"), 1, "single copy")
	var shop = out.get("shop", [])
	assert_eq(shop.size(), 4, "four shop slots")
	if shop.size() == 4:
		assert_eq(shop[0].keys(), ["index", "id", "kind", "tier", "price", "advisor_score", "locked"], "shop keys")
		assert_eq(shop[0].get("price"), 25, "shop[0].price copied")
		assert_eq(shop[0].get("advisor_score"), 31.5, "shop[0].advisor_score")
		assert_eq(shop[3].get("index"), 3, "index added")
		assert_eq(shop[1].get("locked"), true, "locked copied")
	assert_eq(out.get("levelup_options"), [], "no level-up on screen")
	assert_eq(out.get("unlocks_this_run"), ["chal_well_rounded"], "unlocks")
	var recent = out.get("recent", [])
	assert_eq(recent.size(), 10, "recent capped at the last 10")
	if recent.size() == 10:
		assert_eq(recent[0].get("i"), 2.0, "oldest kept is the third")
		assert_eq(recent[9].get("i"), 11.0, "newest last")
	assert_eq(out.get("plan_id"), "wr-ranged-v2", "plan_id")
	assert_eq(out.get("target_challenge"), "chal_well_rounded", "target_challenge")


# Missing sections degrade to empty values, never an error.
func test_serialize_empty_parts():
	var out = StateExport.serialize({}, {"kind": "advise", "run_id": "norun", "seq": 1, "clock": CLOCK})
	assert_eq(out.keys(), KEYS, "all keys present")
	assert_eq(out.get("hp"), null, "hp null when unknown")
	assert_eq(out.get("shop"), [], "shop empty")
	assert_eq(out.get("levelup_options"), [], "levelup empty")
	assert_eq(out.get("stats").size(), 0, "stats empty")
	assert_eq(out.get("plan_id"), "", "plan_id empty")


func test_serialize_levelup_options_get_index():
	var parts = {"levelup_options": [
		{"stat": "stat_max_hp", "value": 3, "advisor_score": 12.25},
		{"stat": "stat_armor", "value": 1, "advisor_score": 0.0}]}
	var out = StateExport.serialize(parts, _meta())
	var opts = out.get("levelup_options", [])
	assert_eq(opts.size(), 2, "two options")
	if opts.size() == 2:
		assert_eq(opts[1].keys(), ["index", "stat", "value", "advisor_score"], "option keys")
		assert_eq(opts[1].get("index"), 1, "index")
		assert_eq(opts[0].get("value"), 3, "value int")
		assert_eq(opts[0].get("advisor_score"), 12.25, "score")


func test_file_name_pads_seq():
	assert_eq(StateExport.file_name("20261021-090000-well_rounded-d2", 7, CLOCK),
			"20261021-090000-well_rounded-d2-007.json", "in-run name: run_id and padded seq")
	assert_eq(StateExport.file_name("r", 1234), "r-1234.json", "wider seq not truncated")
	assert_eq(StateExport.file_name("norun", 7, CLOCK), "norun-20261021-090507-007.json",
			"no open run: timestamped from the export clock")


func test_effective_plan_id():
	var plan = {"plan_id": "wr-ranged-v2", "character_id": "character_well_rounded", "plan": {}}
	assert_eq(StateExport.effective_plan_id(null, "character_well_rounded"), "builtin", "no plan file")
	assert_eq(StateExport.effective_plan_id(plan, "character_ranger"), "builtin", "plan for another character")
	assert_eq(StateExport.effective_plan_id(plan, "character_well_rounded"), "wr-ranged-v2", "matching character")


# A collected shop entry carries its on-screen slot; serialize keeps it.
func test_serialize_shop_index_passes_through():
	var parts = {"shop": [{"index": 5, "id": "item_helmet", "kind": "item", "tier": 0,
			"price": 14.0, "advisor_score": 4.0, "locked": false}]}
	var out = StateExport.serialize(parts, _meta())
	assert_eq(out.get("shop", []).size(), 1, "one entry")
	if out.get("shop", []).size() == 1:
		assert_eq(out.shop[0].get("index"), 5, "index from the part, not the list position")


func test_export_state_writes_file():
	var dir = "user://brotato-bot/test-state-%d" % OS.get_ticks_usec()
	var data = StateExport.serialize(_parts(), _meta())
	var path = StateExport.write(dir, "20261021-090000-well_rounded-d2", 3, data)
	assert_eq(path, dir + "/20261021-090000-well_rounded-d2-003.json", "returned path")
	var listed = []
	var ld = Directory.new()
	if ld.open(dir) == OK:
		ld.list_dir_begin(true, true)
		var fn = ld.get_next()
		while fn != "":
			listed.append(fn)
			fn = ld.get_next()
		ld.list_dir_end()
	assert_eq(listed, ["20261021-090000-well_rounded-d2-003.json"], "written atomically: no .tmp left")
	var f = File.new()
	if f.open(path, File.READ) != OK:
		failures.append("cannot read back %s" % path)
	else:
		var parsed = JSON.parse(f.get_as_text())
		f.close()
		assert_eq(parsed.error, OK, "written file parses")
		if parsed.error == OK:
			assert_eq(parsed.result.get("kind"), "advise", "kind round-trips")
			assert_eq(parsed.result.get("gold"), 63.0, "gold round-trips (JSON float)")
			assert_eq(parsed.result.get("shop").size(), 4, "shop round-trips")
	var d = Directory.new()
	d.remove(path)
	d.remove(dir)
	assert_false(d.dir_exists(dir), "test dir cleaned up")


func test_export_id_matches_the_file_name():
	var clock = {"year": 2026, "month": 10, "day": 22, "hour": 10, "minute": 15, "second": 0}
	assert_eq(StateExport.export_id("norun", 7, clock), "norun-20261022-101500-007", "norun id")
	assert_eq(StateExport.export_id("run-a", 3, clock), "run-a-003", "run id")
	assert_eq(StateExport.export_id("norun", 7, clock) + ".json", StateExport.file_name("norun", 7, clock),
		"id is the state file's base name")
