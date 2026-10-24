extends "res://mod/tests/test_base.gd"

const SetScore = preload("res://mod/Ellie-BrotatoBot/shopping/set_score.gd")


func test_one_set_is_a_sixth_of_the_value():
	assert_eq(SetScore.bonus(["set_blunt"], {"set_blunt": 12.0}), 2.0, "12 / 6")


func test_two_sets_sum():
	assert_eq(SetScore.bonus(["set_blunt", "set_primitive"], {"set_blunt": 12.0, "set_primitive": 6}), 3.0, "2 + 1")


func test_unknown_set_and_empty_map_score_zero():
	assert_eq(SetScore.bonus(["set_gun"], {"set_blunt": 12.0}), 0.0, "unknown set")
	assert_eq(SetScore.bonus(["set_blunt"], {}), 0.0, "empty map")
	assert_eq(SetScore.bonus([], {"set_blunt": 12.0}), 0.0, "no sets")


func test_non_numeric_value_is_ignored():
	assert_eq(SetScore.bonus(["set_blunt", "set_gun"], {"set_blunt": "big", "set_gun": 6.0}), 1.0, "string skipped")
