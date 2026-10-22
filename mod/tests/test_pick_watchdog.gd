extends "res://mod/tests/test_base.gd"

const PickWatchdog = preload("res://mod/Ellie-BrotatoBot/core/pick_watchdog.gd")


func test_stall_is_measured_in_time_not_frames():
	assert_false(PickWatchdog.stalled(1000, 0, false), "1 s without progress is not a stall")
	assert_false(PickWatchdog.stalled(1500, 0, false), "exactly the limit is not a stall")
	assert_true(PickWatchdog.stalled(1501, 0, false), "past 1.5 s is a stall")
	assert_eq(PickWatchdog.STALL_MS, 1500, "limit")


func test_never_a_stall_while_paused():
	assert_false(PickWatchdog.stalled(99999, 0, true), "a paused tree freezes the pick timer")
