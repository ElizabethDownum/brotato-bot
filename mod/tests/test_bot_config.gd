extends "res://mod/tests/test_base.gd"

const BotConfig = preload("res://mod/Ellie-BrotatoBot/core/bot_config.gd")


func test_defaults_when_file_missing():
	var c = BotConfig.load_from("res://mod/tests/fixtures/does_not_exist.json")
	assert_eq(c.bot_profile_id, 1, "bot_profile_id")
	assert_eq(c.request_timeout_ms, 45000, "request_timeout_ms")
	assert_eq(c.checkpoint_timeout_ms, 120000, "checkpoint_timeout_ms")
	assert_eq(c.ask_tie_margin, 3.0, "ask_tie_margin")
	assert_eq(c.ask_floor, 8.0, "ask_floor")
	assert_eq(c.target_challenge, "", "target_challenge")
	assert_eq(c.export_hotkey, "F9", "export_hotkey")
	assert_eq(BotConfig.DEFAULT_PATH, "user://brotato-bot/config.json", "DEFAULT_PATH")


func test_partial_file_overrides_only_given_keys():
	var c = BotConfig.load_from("res://mod/tests/fixtures/config_partial.json")
	assert_eq(c.ask_floor, 12.0, "ask_floor overridden")
	assert_eq(c.bot_profile_id, 1, "bot_profile_id default kept")
	assert_eq(c.request_timeout_ms, 45000, "request_timeout_ms default kept")
	assert_eq(c.export_hotkey, "F9", "export_hotkey default kept")
