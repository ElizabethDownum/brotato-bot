extends "res://mod/tests/test_base.gd"

const Checkpoint = preload("res://mod/Ellie-BrotatoBot/core/checkpoint.gd")


func test_is_target_matches_only_a_non_empty_equal_id():
	assert_true(Checkpoint.is_target("chal_gatherer_1", "chal_gatherer_1"), "same id")
	assert_false(Checkpoint.is_target("chal_gatherer_2", "chal_gatherer_1"), "other id")
	assert_false(Checkpoint.is_target("", ""), "no target set never matches")
	assert_false(Checkpoint.is_target("chal_rookie", ""), "empty target never matches")


func test_due_after_target_fires_once_before_the_final_wave():
	assert_true(Checkpoint.due(true, false, 5, 20, false), "fired, not done, wave 5 of 20")
	assert_false(Checkpoint.due(false, false, 5, 20, false), "target not fired")
	assert_false(Checkpoint.due(true, true, 5, 20, false), "checkpoint already done")
	assert_true(Checkpoint.due(true, false, 19, 20, false), "wave 19 still checkpoints")


func test_due_skips_the_final_wave_of_a_normal_run():
	# The Task 7 completion gate owns the last wave.
	assert_false(Checkpoint.due(true, false, 20, 20, false), "wave 20 of 20")
	assert_false(Checkpoint.due(true, false, 21, 20, false), "past the last wave")


func test_due_continues_past_wave_20_in_endless():
	assert_true(Checkpoint.due(true, false, 20, 20, true), "endless wave 20")
	assert_true(Checkpoint.due(true, false, 27, 20, true), "endless wave 27")


func _w(response, source, acting = true):
	var out = Checkpoint.wanted(response, source, acting)
	return "%s/%s" % [out.applied, out.reason]


func test_wanted_maps_a_response_to_revise_plan_skip_or_timeout():
	assert_eq(_w(null, "timeout"), "timeout/", "no response")
	assert_eq(_w({"action": "revise_plan", "plan_patch": {}}, "haiku"), "revise_plan/", "revise_plan")
	assert_eq(_w({"action": "skip"}, "haiku"), "skip/", "skip")
	assert_eq(_w({"action": "buy", "option_index": 0}, "haiku"), "skip/", "other actions are skip")
	assert_eq(_w({"action": "revise_plan"}, "haiku"), "skip/", "revise_plan without a patch dict is skip")
	assert_eq(_w({}, "haiku"), "skip/", "no action is skip")


func test_wanted_names_why_no_answer_came():
	assert_eq(_w(null, "interrupted"), "skip/interrupted", "human unpause")
	assert_eq(_w(null, "invalid"), "skip/invalid", "invalid response")
	assert_eq(_w(null, "busy"), "skip/busy", "another decision in flight")


func test_wanted_never_applies_after_a_halt():
	assert_eq(_w({"action": "revise_plan", "plan_patch": {"a": 1}}, "haiku", false), "skip/halted",
		"revise_plan after a halt")
	assert_eq(_w(null, "timeout", false), "skip/halted", "halted while waiting")
	assert_eq(_w({"action": "skip"}, "haiku", false), "skip/halted", "skip after a halt")
	assert_eq(_w(null, "interrupted", false), "skip/interrupted", "explicit source wins over halted")
