extends "res://mod/tests/test_base.gd"

# BotRuntime.complete() touches game globals, so only its pure outcome mapping
# (Guards.normalize_outcome) runs headlessly.

const Guards = preload("res://mod/Ellie-BrotatoBot/core/guards.gd")


func test_normalize_outcome_maps_won_to_win():
	assert_eq(Guards.normalize_outcome("won"), "win")


func test_normalize_outcome_keeps_win():
	assert_eq(Guards.normalize_outcome("win"), "win")


func test_normalize_outcome_keeps_death():
	assert_eq(Guards.normalize_outcome("death"), "death")


func test_normalize_outcome_coerces_unknown_to_death():
	assert_eq(Guards.normalize_outcome("quit"), "death")
