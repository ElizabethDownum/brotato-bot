extends "res://mod/tests/test_base.gd"

const HumanPause = preload("res://mod/Ellie-BrotatoBot/core/human_pause.gd")


func _key(scancode, pressed):
	var ev = InputEventKey.new()
	ev.scancode = scancode
	ev.pressed = pressed
	return ev


func test_may_continue_needs_may_act():
	assert_true(HumanPause.may_continue(true, false, "acting", false), "acting, unpaused")
	assert_false(HumanPause.may_continue(false, false, "acting", false), "halted (may_act false)")


func test_may_continue_stops_when_paused_outside_a_decision():
	assert_false(HumanPause.may_continue(true, true, "acting", false), "paused by someone else")
	assert_true(HumanPause.may_continue(true, true, "deciding", false), "paused by decide()")


func test_may_continue_stops_after_a_human_pause():
	assert_false(HumanPause.may_continue(true, false, "acting", true), "she paused, then resumed")
	assert_false(HumanPause.may_continue(true, true, "deciding", true), "she paused during a decision")


func test_unpause_after_decide_only_when_decide_paused_and_no_menu_open():
	assert_true(HumanPause.unpause_after_decide(false, false), "decide paused, no menu")
	assert_false(HumanPause.unpause_after_decide(false, true), "pause menu open: leave it paused")
	assert_false(HumanPause.unpause_after_decide(true, false), "tree was already paused")
	assert_false(HumanPause.unpause_after_decide(true, true), "already paused, menu open")


func test_deciding_input_escape_release_is_escape():
	assert_eq(HumanPause.deciding_input(_key(KEY_ESCAPE, false), [KEY_W]), "escape", "ESC released")
	assert_eq(HumanPause.deciding_input(_key(KEY_ESCAPE, true), [KEY_W]), "", "ESC press waits for release")


func test_deciding_input_move_key_is_move():
	assert_eq(HumanPause.deciding_input(_key(KEY_W, true), [KEY_W]), "move", "W pressed")
	assert_eq(HumanPause.deciding_input(_key(KEY_W, false), [KEY_W]), "", "W released")
	assert_eq(HumanPause.deciding_input(_key(KEY_F9, true), [KEY_W]), "", "F9 is neither")
	var pad = InputEventJoypadButton.new()
	pad.button_index = 0
	pad.pressed = true
	assert_eq(HumanPause.deciding_input(pad, [KEY_W]), "move", "joypad button")


func test_deciding_input_ignores_the_mouse():
	assert_eq(HumanPause.deciding_input(InputEventMouseMotion.new(), [KEY_W]), "", "mouse motion")
