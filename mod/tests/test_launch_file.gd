extends "res://mod/tests/test_base.gd"

const LaunchFile = preload("res://mod/Ellie-BrotatoBot/core/launch_file.gd")

const GOOD = '{"token": "t1", "character_id": "character_old", "starting_weapon": "weapon_rock", "danger": 4, "target_challenge": "chal_slow", "created_at": "2026-10-23T10:00:00"}'


func test_valid_file_parses_with_int_danger():
	var d = LaunchFile.parse(GOOD)
	assert_eq(typeof(d), TYPE_DICTIONARY, "dictionary")
	if typeof(d) != TYPE_DICTIONARY:
		return
	assert_eq(d.token, "t1", "token")
	assert_eq(d.character_id, "character_old", "character_id")
	assert_eq(d.starting_weapon, "weapon_rock", "starting_weapon")
	assert_eq(d.danger, 4, "danger is an int")
	assert_eq(LaunchFile.DEFAULT_PATH, "user://brotato-bot/launch.json", "DEFAULT_PATH")


func test_bad_files_give_null():
	assert_eq(typeof(LaunchFile.parse("not json")), TYPE_NIL, "bad JSON")
	assert_eq(typeof(LaunchFile.parse("[1]")), TYPE_NIL, "not an object")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"token": "t1", ', ""))), TYPE_NIL, "missing token")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"t1"', "7"))), TYPE_NIL, "token not a string")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": "4"'))), TYPE_NIL, "danger a string")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": 2.5'))), TYPE_NIL, "danger fractional")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": 6'))), TYPE_NIL, "danger above 5")
	assert_eq(typeof(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": -1'))), TYPE_NIL, "danger below 0")
	assert_eq(typeof(LaunchFile.load_from("res://mod/tests/fixtures/no_launch.json")), TYPE_NIL, "missing file")


func test_danger_bounds_are_inclusive():
	assert_eq(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": 0')).danger, 0, "0")
	assert_eq(LaunchFile.parse(GOOD.replace('"danger": 4', '"danger": 5')).danger, 5, "5")


func test_load_from_reads_a_file():
	var path = "user://test_launch_file.json"
	var f = File.new()
	f.open(path, File.WRITE)
	f.store_string(GOOD)
	f.close()
	var d = LaunchFile.load_from(path)
	assert_eq(d.token if typeof(d) == TYPE_DICTIONARY else "", "t1", "read back")
	Directory.new().remove(path)


func test_weapon_candidates_per_tier_form_first():
	assert_eq(LaunchFile.weapon_candidates("weapon_rock"), ["weapon_rock_1", "weapon_rock"], "tier form then bare id")


func test_difficulty_id():
	assert_eq(LaunchFile.difficulty_id(0), "difficulty_0", "0")
	assert_eq(LaunchFile.difficulty_id(5), "difficulty_5", "5")
