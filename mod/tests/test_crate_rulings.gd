extends "res://mod/tests/test_base.gd"

const CrateRulings = preload("res://mod/Ellie-BrotatoBot/core/crate_rulings.gd")


func test_crate_reuses_take_and_recycle_with_original_decision_id():
	for action in ["take", "recycle"]:
		var cache = CrateRulings.new()
		assert_true(cache.answer(5, 0, "item_ghost").empty(), "first copy has no answer")
		cache.remember(5, 0, "item_ghost", action, "run-001")
		assert_eq(cache.answer(5, 0, "item_ghost").action, action, "another copy uses the original action")
		assert_eq(cache.answer(5, 0, "item_ghost").id, "run-001", "another copy uses the original decision id")
		cache.remember(5, 0, "item_ghost", action, "run-002")
		assert_eq(cache.answer(5, 0, "item_ghost").id, "run-001", "reuse keeps the first decision id")


func test_crate_distinct_items_and_players_do_not_share_rulings():
	var cache = CrateRulings.new()
	cache.remember(5, 0, "item_a", "take", "run-001")
	assert_true(cache.answer(5, 0, "item_b").empty(), "different item asks separately")
	assert_true(cache.answer(5, 1, "item_a").empty(), "different build asks separately")
	cache.remember(5, 1, "item_a", "recycle", "run-002")
	assert_eq(cache.answer(5, 0, "item_a").action, "take", "player zero keeps its choice")
	assert_eq(cache.answer(5, 1, "item_a").action, "recycle", "player one keeps its choice")


func test_crate_next_wave_clears_every_players_answers():
	var cache = CrateRulings.new()
	cache.remember(5, 0, "item_a", "take", "run-001")
	cache.remember(5, 1, "item_b", "recycle", "run-002")
	assert_true(cache.answer(6, 0, "item_a").empty(), "next wave asks again")
	assert_true(cache.answer(6, 1, "item_b").empty(), "next wave clears other players too")
	cache.remember(6, 0, "item_a", "recycle", "run-003")
	assert_eq(cache.answer(6, 0, "item_a").id, "run-003", "new wave can reverse the ruling")


func test_crate_remember_also_resets_the_wave():
	var cache = CrateRulings.new()
	cache.remember(5, 0, "item_a", "take", "run-001")
	cache.remember(6, 0, "item_b", "take", "run-002")
	assert_true(cache.answer(6, 0, "item_a").empty(), "remember cannot carry an old answer forward")
	assert_eq(cache.answer(6, 0, "item_b").id, "run-002", "new wave answer retained")


func test_crate_unsupported_actions_are_not_rulings():
	var cache = CrateRulings.new()
	for action in ["", "timeout", "rule", "buy", "skip"]:
		cache.remember(5, 0, "item_a", action, "run-001")
		assert_true(cache.answer(5, 0, "item_a").empty(), "not a take/recycle: " + action)
