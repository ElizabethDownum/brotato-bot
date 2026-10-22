extends "res://mod/tests/test_base.gd"

const Guards = preload("res://mod/Ellie-BrotatoBot/core/guards.gd")
const BotPaths = preload("res://mod/Ellie-BrotatoBot/core/bot_paths.gd")

const TEST_DIR = "user://brotato-bot/test-guards"
const VALID_PLAN = '{"plan_id": "t", "character_id": "character_well_rounded", "plan": {}}'


func _key(scancode, pressed = true):
	var ev = InputEventKey.new()
	ev.scancode = scancode
	ev.pressed = pressed
	return ev


func _button(index, pressed):
	var ev = InputEventJoypadButton.new()
	ev.button_index = index
	ev.pressed = pressed
	return ev


func _axis(axis, value):
	var ev = InputEventJoypadMotion.new()
	ev.axis = axis
	ev.axis_value = value
	return ev


func test_profile_ok_only_for_bot_profile():
	var cfg = {"bot_profile_id": 1}
	assert_true(Guards.profile_ok(1, cfg), "profile 1")
	assert_false(Guards.profile_ok(0, cfg), "profile 0")
	assert_false(Guards.profile_ok(2, cfg), "profile 2")
	# JSON numbers arrive as floats.
	assert_true(Guards.profile_ok(2, {"bot_profile_id": 2.0}), "float config value")
	# Missing key defaults to profile 1.
	assert_true(Guards.profile_ok(1, {}), "default bot profile is 1")
	assert_false(Guards.profile_ok(0, {}), "default never allows profile 0")


func test_profile_zero_is_never_the_bot_profile():
	assert_false(Guards.profile_ok(0, {"bot_profile_id": 0}), "config 0 does not admit profile 0")
	assert_false(Guards.profile_ok(0, {"bot_profile_id": 0.0}), "float config 0 either")


func test_human_input_detects_move_actions():
	assert_true(Guards.is_human_move(_key(KEY_W)), "W pressed")
	assert_false(Guards.is_human_move(_key(KEY_F9)), "F9 pressed")
	assert_false(Guards.is_human_move(_key(KEY_W, false)), "W released")
	assert_false(Guards.is_human_move(_key(KEY_SPACE)), "Space is not a move key")
	assert_true(Guards.is_human_move(_key(KEY_LEFT)), "arrow left")
	assert_true(Guards.is_human_move(_axis(0, 0.9)), "axis 0 at 0.9")
	assert_true(Guards.is_human_move(_axis(3, -0.8)), "axis 3 at -0.8")
	assert_false(Guards.is_human_move(_axis(0, 0.1)), "axis 0 at 0.1")
	assert_false(Guards.is_human_move(_axis(6, 1.0)), "trigger axis 6")
	assert_false(Guards.is_human_move(InputEventMouseMotion.new()), "mouse ignored")
	assert_true(Guards.is_human_move(_key(KEY_I)), "I is in the fallback set (button_move_up)")
	assert_true(Guards.is_human_move(_key(KEY_L)), "L is in the fallback set")
	var echo = _key(KEY_D)
	echo.echo = true
	assert_true(Guards.is_human_move(echo), "echo of a held move key counts")
	assert_true(Guards.is_human_move(_button(12, true)), "d-pad button 12 pressed")
	assert_true(Guards.is_human_move(_button(0, true)), "any pressed joypad button")
	assert_false(Guards.is_human_move(_button(12, false)), "joypad button released")
	assert_false(Guards.is_human_move(_button(0, true), null, [12, 13, 14, 15]), "custom button set excludes 0")
	assert_true(Guards.is_human_move(InputEventMouseMotion.new(), null, null, true), "mouse motion in mouse_only")
	assert_false(Guards.is_human_move(InputEventMouseMotion.new(), null, null, false), "mouse motion otherwise")
	var click = InputEventMouseButton.new()
	click.button_index = BUTTON_LEFT
	click.pressed = true
	assert_true(Guards.is_human_move(click, null, null, true), "mouse click in mouse_only")
	assert_false(Guards.is_human_move(click), "mouse click otherwise")
	click.pressed = false
	assert_false(Guards.is_human_move(click, null, null, true), "mouse release in mouse_only")
	# Explicit scancode set overrides the default.
	assert_true(Guards.is_human_move(_key(KEY_J), [KEY_J]), "custom set J")
	assert_false(Guards.is_human_move(_key(KEY_W), [KEY_J]), "custom set excludes W")


func test_focus_setting_ok():
	assert_true(Guards.focus_setting_ok({"pause_on_focus_lost": false}), "false is ok")
	assert_false(Guards.focus_setting_ok({"pause_on_focus_lost": true}), "true is not ok")
	assert_false(Guards.focus_setting_ok({}), "missing key is not ok")


func test_plan_present():
	var d = Directory.new()
	if d.make_dir_recursive(TEST_DIR) != OK:
		failures.append("could not create %s" % TEST_DIR)
		return
	var path = TEST_DIR.plus_file("plan.json")
	assert_false(Guards.plan_present(path), "absent before write")
	var f = File.new()
	if f.open(path, File.WRITE) == OK:
		f.store_string("{}")
		f.close()
	assert_true(Guards.plan_present(path), "present after write")
	d.remove(path)
	d.remove(TEST_DIR)
	assert_false(Guards.plan_present(path), "absent after remove")


func test_enable_refusal_reason():
	var cfg = {"bot_profile_id": 1}
	var missing = TEST_DIR.plus_file("no-plan.json")
	assert_eq(Guards.enable_refusal(0, cfg, missing), "wrong profile (0)", "profile 0 checked first")
	assert_eq(Guards.enable_refusal(1, cfg, missing), "no plan at %s" % missing, "no plan")
	var d = Directory.new()
	if d.make_dir_recursive(TEST_DIR) != OK:
		failures.append("could not create %s" % TEST_DIR)
		return
	var path = TEST_DIR.plus_file("plan.json")
	var f = File.new()
	if f.open(path, File.WRITE) == OK:
		f.store_string(VALID_PLAN)
		f.close()
	assert_eq(Guards.enable_refusal(1, cfg, path), "", "allowed")
	assert_eq(Guards.enable_refusal(0, cfg, path), "wrong profile (0)", "plan does not override profile")
	d.remove(path)
	d.remove(TEST_DIR)


func test_enable_refusal_for_an_invalid_plan():
	var cfg = {"bot_profile_id": 1}
	var bad = "res://mod/tests/fixtures/plan_invalid.json"
	assert_eq(Guards.enable_refusal(1, cfg, bad), "invalid plan at %s" % bad, "malformed plan.json")
	assert_eq(Guards.enable_refusal(0, cfg, bad), "wrong profile (0)", "profile still checked first")
	assert_eq(Guards.enable_refusal(1, cfg, "res://mod/tests/fixtures/plan_valid.json"), "", "valid plan")
