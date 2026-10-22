extends "res://mod/tests/test_base.gd"

const PlanFile = preload("res://mod/Ellie-BrotatoBot/core/plan_file.gd")


func test_valid_plan_loads():
	var p = PlanFile.load_from("res://mod/tests/fixtures/plan_valid.json")
	assert_eq(typeof(p), TYPE_DICTIONARY, "loaded a dictionary")
	if typeof(p) != TYPE_DICTIONARY:
		return
	assert_eq(p.plan_id, "test-1", "plan_id")
	assert_eq(p.character_id, "character_well_rounded", "character_id")
	assert_eq(p.target_challenge, "chal_test", "target_challenge")
	assert_eq(p.plan.stats.stat_ranged_damage, 9.0, "plan.stats.stat_ranged_damage")
	assert_eq(PlanFile.DEFAULT_PATH, "user://brotato-bot/plan.json", "DEFAULT_PATH")


func test_plan_file_invalid_json_returns_null():
	var p = PlanFile.load_from("res://mod/tests/fixtures/plan_invalid.json")
	assert_eq(typeof(p), TYPE_NIL, "invalid JSON gives null")


func test_plan_file_missing_returns_null():
	var p = PlanFile.load_from("res://mod/tests/fixtures/does_not_exist.json")
	assert_eq(typeof(p), TYPE_NIL, "missing file gives null")


func test_merge_keeps_base_keys_and_deep_merges_stats():
	var base = {
		"weapon_type": "any",
		"stats": {"a": 1, "b": 2},
		"item_bonus": {"x": 1},
		"prefer_weapons": ["w1", "w2"],
		"max_weapons": 6,
	}
	var override = {
		"stats": {"b": 5, "c": 7},
		"item_bonus": {"y": 2},
		"prefer_weapons": ["w3"],
		"weapon_type": "melee",
	}
	var m = PlanFile.merge(base, override)
	_assert_dict_eq(m.stats, {"a": 1, "b": 5, "c": 7}, "stats merged one level deep")
	_assert_dict_eq(m.item_bonus, {"x": 1, "y": 2}, "item_bonus merged one level deep")
	assert_eq(m.prefer_weapons, ["w3"], "non-stats key replaced wholesale")
	assert_eq(m.weapon_type, "melee", "scalar replaced")
	assert_eq(m.max_weapons, 6, "base-only key kept")
	_assert_dict_eq(base.stats, {"a": 1, "b": 2}, "base not mutated")


func test_target_challenge_prefers_plan_then_config():
	var cfg = {"target_challenge": "chal_cfg"}
	assert_eq(PlanFile.target_id({"target_challenge": "chal_plan"}, cfg), "chal_plan", "plan wins")
	assert_eq(PlanFile.target_id({"target_challenge": ""}, cfg), "chal_cfg", "empty plan target falls back")
	assert_eq(PlanFile.target_id(null, cfg), "chal_cfg", "no plan falls back")


func test_apply_only_when_character_matches():
	var built_in = {"weapon_type": "any", "stats": {"a": 1}, "max_rerolls": 15}
	var loaded = PlanFile.load_from("res://mod/tests/fixtures/plan_valid.json")
	var hit = PlanFile.apply(built_in, loaded, "character_well_rounded")
	assert_eq(hit.weapon_type, "ranged", "matching character gets the file plan")
	assert_eq(hit.stats.stat_ranged_damage, 9.0, "file stats merged")
	assert_eq(hit.stats.a, 1, "built-in stats kept")
	assert_eq(hit.max_rerolls, 4, "int plan key normalized from JSON float")
	var miss = PlanFile.apply(built_in, loaded, "character_brawler")
	assert_eq(miss.weapon_type, "any", "other character keeps built-in plan")
	assert_eq(miss.max_rerolls, 15, "other character keeps built-in max_rerolls")
	var none = PlanFile.apply(built_in, null, "character_well_rounded")
	assert_eq(none.weapon_type, "any", "no file keeps built-in plan")


func test_load_cached_reads_file_and_handles_missing():
	var p = PlanFile.load_cached("res://mod/tests/fixtures/plan_valid.json")
	assert_eq(typeof(p), TYPE_DICTIONARY, "cached load returns the plan")
	var again = PlanFile.load_cached("res://mod/tests/fixtures/plan_valid.json")
	assert_true(typeof(again) == TYPE_DICTIONARY and again.plan_id == "test-1", "second call served")
	assert_eq(typeof(PlanFile.load_cached("res://mod/tests/fixtures/does_not_exist.json")), TYPE_NIL, "missing gives null")
	assert_true(PlanFile.mtime("res://mod/tests/fixtures/plan_valid.json") > 0, "mtime of existing file")
	assert_eq(PlanFile.mtime("res://mod/tests/fixtures/does_not_exist.json"), 0, "mtime of missing file")


const TMP_PLAN = "user://test_plan_file_reload.json"


func _write(path, text):
	var f = File.new()
	f.open(path, File.WRITE)
	f.store_string(text)
	f.close()


func _plan_json(rerolls):
	return '{"plan_id": "r", "character_id": "character_well_rounded", "plan": {"max_rerolls": %d}}' % rerolls


# The level-up and shop callers call get_plan every time (no caller-side cache),
# so a rewritten plan file must be seen on the next plan_for call. Godot 3 cannot
# set an mtime and get_modified_time has 1 s resolution, so wait past it.
func test_plan_for_sees_rewritten_file():
	var built_in = {"weapon_type": "any", "max_rerolls": 15}
	_write(TMP_PLAN, _plan_json(4))
	var first = PlanFile.plan_for(built_in, "character_well_rounded", TMP_PLAN)
	assert_eq(first.max_rerolls, 4, "first call reads the file")
	var m1 = PlanFile.mtime(TMP_PLAN)
	OS.delay_msec(1100)
	_write(TMP_PLAN, _plan_json(7))
	assert_true(PlanFile.mtime(TMP_PLAN) > m1, "rewrite advanced the mtime")
	var second = PlanFile.plan_for(built_in, "character_well_rounded", TMP_PLAN)
	assert_eq(second.max_rerolls, 7, "second call sees the rewritten file")
	var other = PlanFile.plan_for(built_in, "character_brawler", TMP_PLAN)
	assert_eq(other.max_rerolls, 15, "other character keeps built-in plan")
	Directory.new().remove(TMP_PLAN)
	var gone = PlanFile.plan_for(built_in, "character_well_rounded", TMP_PLAN)
	assert_eq(gone.max_rerolls, 15, "deleted file falls back to built-in plan")


# Godot 3 compares Dictionaries by identity, so == fails for equal contents.
# Compare key sets and each value with the type-strict assert_eq.
func _assert_dict_eq(a, b, msg):
	assert_eq(typeof(a), TYPE_DICTIONARY, msg + " (is dict)")
	if typeof(a) != TYPE_DICTIONARY:
		return
	assert_eq(a.size(), b.size(), msg + " (size)")
	for k in b.keys():
		assert_true(a.has(k), msg + " (has %s)" % k)
		if a.has(k):
			assert_eq(a[k], b[k], msg + " (key %s)" % k)
