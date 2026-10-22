extends "res://mod/tests/test_base.gd"


const BotPaths = preload("res://mod/Ellie-BrotatoBot/core/bot_paths.gd")
const TestBase = preload("res://mod/tests/test_base.gd")


func test_core_scripts_load():
	assert_eq(BotPaths.ROOT, "user://brotato-bot", "BotPaths.ROOT")


func test_assertions_are_counted():
	var t = TestBase.new()
	assert_eq(t.assertions, 0, "fresh instance")
	t.assert_eq(1, 1)
	t.assert_true(true)
	t.assert_false(false)
	assert_eq(t.assertions, 3, "each assert counts, pass or fail")
	t.assert_eq(1, 2)
	assert_eq(t.assertions, 4, "a failing assert counts too")
	assert_eq(t.failures.size(), 1, "and records its failure")
