extends "res://mod/tests/test_base.gd"

const AskPolicy = preload("res://mod/Ellie-BrotatoBot/core/ask_policy.gd")


func test_two_timeouts_disable_asking():
	var p = AskPolicy.new()
	assert_true(p.allowed(), "asking allowed at first")
	assert_false(p.record("timeout"), "one timeout does not trip")
	assert_true(p.allowed(), "still allowed after one timeout")
	assert_true(p.record("timeout"), "the second consecutive timeout trips")
	assert_false(p.allowed(), "asking disabled")
	assert_false(p.record("timeout"), "trips only once")
	assert_false(p.allowed(), "stays disabled for the run")


func test_an_answer_resets_the_timeout_count():
	var p = AskPolicy.new()
	p.record("timeout")
	p.record("haiku")
	assert_false(p.record("timeout"), "haiku broke the streak")
	p.record("invalid")
	assert_false(p.record("timeout"), "an invalid response is still an answer")
	assert_true(p.allowed(), "allowed")


func test_interrupted_and_busy_do_not_count_or_reset():
	var p = AskPolicy.new()
	p.record("timeout")
	assert_false(p.record("interrupted"), "interrupted is neutral")
	assert_false(p.record("busy"), "busy is neutral")
	assert_true(p.record("timeout"), "the streak survived: second timeout trips")


func test_reset_reenables_asking():
	var p = AskPolicy.new()
	p.record("timeout")
	p.record("timeout")
	p.reset()
	assert_true(p.allowed(), "a new run asks again")
	assert_false(p.record("timeout"), "count restarted")


func test_warning_text():
	assert_eq(AskPolicy.WARNING, "sidecar timeouts; asking disabled for this run", "warning message")
