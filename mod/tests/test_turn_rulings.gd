extends "res://mod/tests/test_base.gd"

const TurnRulings = preload("res://mod/Ellie-BrotatoBot/core/turn_rulings.gd")
const DecisionClient = preload("res://mod/Ellie-BrotatoBot/core/decision_client.gd")


func test_turn_reuses_verdict_and_original_provenance_across_screens():
	for verdict in ["approve", "decline"]:
		for screen in ["crate", "shop"]:
			var store = TurnRulings.new()
			assert_true(store.answer(5, 0, "item_a").empty(), "first copy has no ruling")
			store.remember(5, 0, "item_a", verdict, "run-001", screen)
			var answer = store.answer(5, 0, "item_a")
			assert_eq(answer.verdict, verdict, "either screen reuses the verdict")
			assert_eq(answer.decision_id, "run-001", "original decision id")
			assert_eq(answer.screen, screen, "original screen")
			store.remember(5, 0, "item_a", "decline" if verdict == "approve" else "approve", "run-002", "shop")
			assert_eq(store.answer(5, 0, "item_a").verdict, verdict, "first verdict wins")
			assert_eq(store.answer(5, 0, "item_a").decision_id, "run-001", "reuse preserves id")
			assert_eq(store.answer(5, 0, "item_a").screen, screen, "reuse preserves screen")


func test_turn_distinct_items_and_players_do_not_share_rulings():
	var store = TurnRulings.new()
	store.remember(5, 0, "item_a", "approve", "run-001", "crate")
	assert_true(store.answer(5, 0, "item_b").empty(), "different item asks separately")
	assert_true(store.answer(5, 1, "item_a").empty(), "different build asks separately")
	store.remember(5, 1, "item_a", "decline", "run-002", "shop")
	assert_eq(store.answer(5, 0, "item_a").verdict, "approve", "player zero keeps its choice")
	assert_eq(store.answer(5, 1, "item_a").verdict, "decline", "player one keeps its choice")


func test_turn_next_wave_clears_every_players_answers():
	var store = TurnRulings.new()
	store.remember(5, 0, "item_a", "approve", "run-001", "crate")
	store.remember(5, 1, "item_b", "decline", "run-002", "shop")
	assert_true(store.answer(6, 0, "item_a").empty(), "next wave asks again")
	assert_true(store.answer(6, 1, "item_b").empty(), "next wave clears other players too")
	store.remember(6, 0, "item_a", "decline", "run-003", "crate")
	assert_eq(store.answer(6, 0, "item_a").decision_id, "run-003", "new turn can reverse the ruling")


func test_turn_remember_also_resets_the_wave():
	var store = TurnRulings.new()
	store.remember(5, 0, "item_a", "approve", "run-001", "crate")
	store.remember(6, 0, "item_b", "approve", "run-002", "shop")
	assert_true(store.answer(6, 0, "item_a").empty(), "remember cannot carry an old answer forward")
	assert_eq(store.answer(6, 0, "item_b").decision_id, "run-002", "new wave answer retained")


func test_turn_explicit_reset_handles_new_run_and_repeated_wave_number():
	var store = TurnRulings.new()
	store.remember(5, 0, "item_a", "approve", "run-001", "crate")
	store.reset(5)
	assert_true(store.answer(5, 0, "item_a").empty(), "Hourglass can repeat a wave with a fresh turn")
	store.remember(5, 0, "item_a", "decline", "run-002", "shop")
	store.remember(5, 1, "item_b", "approve", "run-003", "crate")
	store.reset()
	assert_true(store.answer(5, 0, "item_a").empty(), "new run clears same-wave ruling")
	assert_true(store.answer(5, 1, "item_b").empty(), "new run clears all players")


func test_turn_unsupported_verdicts_and_locks_are_not_rulings():
	var store = TurnRulings.new()
	for verdict in ["", "timeout", "rule", "buy", "pass", "take", "recycle", "lock", "skip"]:
		store.remember(5, 0, "item_a", verdict, "run-001", "shop")
		assert_true(store.answer(5, 0, "item_a").empty(), "not a verdict: " + verdict)


func test_turn_shop_view_sees_crate_and_later_shop_verdicts():
	var store = TurnRulings.new()
	store.remember(5, 0, "item_a", "decline", "run-001", "crate")
	var ruled = store.for_player(5, 0)
	assert_eq(ruled.item_a.verdict, "decline", "shop inherits crate decline")
	store.remember(5, 0, "item_b", "approve", "run-002", "shop")
	assert_eq(ruled.item_b.verdict, "approve", "shop view sees new applied ruling")
	assert_eq(store.answer(5, 0, "item_b").screen, "shop", "crate lookup sees shop provenance")
	assert_true(store.for_player(6, 0).empty(), "next wave has a fresh shop view")


func test_turn_crate_verdicts_suppress_shop_asks_but_allow_new_triggers():
	var store = TurnRulings.new()
	var cfg = {"ask_per_visit": 2}
	for verdict in ["approve", "decline"]:
		store.reset(5)
		store.remember(5, 0, "old", verdict, "run-001", "crate")
		var ruled = store.for_player(5, 0)
		var entries = [
			{"node": "old", "id": "old", "kind": "item", "score": 20.0, "price": 100},
			{"node": "a", "id": "a", "kind": "item", "score": 10.0, "price": 20},
			{"node": "b", "id": "b", "kind": "item", "score": 9.0, "price": 20}]
		var board = DecisionClient.shop_options(entries, 400, ruled)
		assert_eq(DecisionClient.should_ask(board.scores, board.affordable, cfg,
			board.ids, ["old"], 6.0, 400, board.prices, 0, ruled),
			"" if verdict == "approve" else "ask", "approved best buys first; declined best leaves the new tie")
		board = DecisionClient.shop_options(entries, 50, ruled)
		assert_eq(DecisionClient.should_ask(board.scores, board.affordable, cfg,
			board.ids, ["old"], 6.0, 50, board.prices, 0, ruled), "ask", "tie asks when old is unaffordable or declined")
		assert_eq(DecisionClient.should_ask([20.0], [0], cfg,
			["old"], ["old"], 6.0, 50, [10], 0, store.for_player(5, 1)), "pivot", "other player can ask")
