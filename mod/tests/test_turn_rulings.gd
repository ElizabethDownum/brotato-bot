extends "res://mod/tests/test_base.gd"

const TurnRulings = preload("res://mod/Ellie-BrotatoBot/core/turn_rulings.gd")
const DecisionClient = preload("res://mod/Ellie-BrotatoBot/core/decision_client.gd")


func test_rule_gate_requires_review_approval_for_every_acquisition_path():
	var review = ["item_ghost", "weapon_review"]
	for id in review:
		for reason in ["declined", "timeout", "invalid", "sidecar-down", "budget-spent", "lock"]:
			var ruled = {id: {"verdict": "decline"}} if reason == "declined" else {}
			assert_false(TurnRulings.rule_allowed(id, review, ruled), "no sign-off: " + reason)
		assert_true(TurnRulings.rule_allowed(id, review, {id: {"verdict": "approve"}}), "sign-off permits rules")
	assert_true(TurnRulings.rule_allowed("ordinary", review, {}), "ordinary unruled option is allowed")
	assert_false(TurnRulings.rule_allowed("ordinary", review, {"ordinary": {"verdict": "decline"}}), "explicit veto also binds ordinary options")


func test_shop_automatic_declines_for_each_applied_action():
	var ids = ["item_ghost", "ordinary", "weapon_review"]
	for act in ["buy", "reroll", "skip", "pass", "lock", "revise_plan"]:
		var store = TurnRulings.new()
		var r = {"action": act, "option_index": 0}
		var result = store.shop_rulings(5, 0, ids, ["item_ghost", "weapon_review"], r, "run-001", act)
		assert_eq(result.declined, [2] if act == "buy" else [0, 2], "automatic review declines: " + act)
		assert_eq(result.missing, 3, "missing counted before action override")
		var answer = store.answer(5, 0, "weapon_review")
		assert_eq(answer.verdict, "decline", "recorded verdict")
		assert_eq(answer.decision_id, "run-001", "decision provenance")
		assert_eq(answer.screen, "shop", "screen provenance")
		if act == "buy":
			assert_eq(store.answer(5, 0, "item_ghost").verdict, "approve", "applied buy signs off target")
		assert_true(store.answer(5, 0, "ordinary").empty(), "ordinary option needs explicit decline")


func test_rule_gate_rechecks_plan_changes_and_new_wave_before_saving():
	var store = TurnRulings.new()
	var ruled = store.for_player(5, 0)
	assert_true(TurnRulings.rule_allowed("weapon_b", [], ruled), "ordinary saving target allowed")
	assert_false(TurnRulings.rule_allowed("weapon_b", ["weapon_b"], ruled), "new review requirement invalidates old saving eligibility")
	store.remember(5, 0, "weapon_b", "approve", "run-001", "shop")
	assert_true(TurnRulings.rule_allowed("weapon_b", ["weapon_b"], ruled), "approval restores saving eligibility")
	assert_false(TurnRulings.rule_allowed("weapon_b", ["weapon_b"], store.for_player(6, 0)), "carried lock needs new-wave approval")


func test_shop_pass_declines_ordinary_target_and_review_items():
	var store = TurnRulings.new()
	var result = store.shop_rulings(5, 0, ["ordinary", "review"], ["review"],
		{"action": "pass", "option_index": 0}, "run-001", "pass")
	assert_eq(result.declined, [1, 0], "implicit review and pass veto")
	assert_false(TurnRulings.rule_allowed("ordinary", [], store.for_player(5, 0)), "pass binds rules")


func test_shop_unapplied_answer_does_not_implicitly_decline():
	var store = TurnRulings.new()
	for act in ["buy", "lock", "reroll", "pass", "revise_plan"]:
		var result = store.shop_rulings(5, 0, ["a", "b"], ["a", "b"],
			{"action": act, "option_index": 0}, "run-001", "rule")
		assert_eq(result.declined, [], "failed action: " + act)
		assert_eq(result.missing, 2, "failed action still reports missing")
	assert_true(store.for_player(5, 0).empty(), "a later board may ask again")


func test_shop_complete_rulings_record_approve_and_decline_with_action_precedence():
	for act in ["buy", "lock", "reroll", "skip", "pass", "revise_plan"]:
		var store = TurnRulings.new()
		var r = {"action": act, "option_index": 0, "rulings": [
			{"option_index": 0, "verdict": "approve"}, {"option_index": 1, "verdict": "decline"}]}
		var result = store.shop_rulings(5, 0, ["a", "b"], ["a"], r, "run-001", act)
		assert_eq(result.declined, [0, 1] if act == "pass" else [1], "action precedence: " + act)
		assert_eq(result.missing, 0, "complete answer")
		assert_eq(store.answer(5, 0, "a").verdict, "decline" if act == "pass" else "approve", "record explicit approval")
		assert_eq(store.answer(5, 0, "b").verdict, "decline", "ordinary item explicitly vetoed")
		assert_eq(store.answer(5, 0, "a").decision_id, "run-001", "approval provenance")
		assert_eq(store.answer(5, 0, "b").decision_id, "run-001", "decline provenance")


func test_shop_explicit_declines_apply_even_when_primary_action_cannot_land():
	var store = TurnRulings.new()
	var result = store.shop_rulings(5, 0, ["a", "b", "c"], ["a"],
		{"action": "buy", "option_index": 0, "rulings": [
			{"option_index": 1, "verdict": "decline"}, {"option_index": 2, "verdict": "approve"}]}, "run-001", "rule")
	assert_eq(result.declined, [1], "explicit verdicts are independent")
	assert_true(store.answer(5, 0, "a").empty(), "failed buy gives no implicit verdict")
	assert_eq(store.answer(5, 0, "c").verdict, "approve", "approval applies even when buy fails")


func test_shop_fresh_rulings_replace_old_verdict_and_provenance():
	var store = TurnRulings.new()
	store.remember(5, 0, "a", "approve", "crate-001", "crate")
	store.shop_rulings(5, 0, ["a"], [], {"action": "skip", "rulings": [
		{"option_index": 0, "verdict": "decline"}]}, "shop-002", "skip")
	assert_eq(store.answer(5, 0, "a").verdict, "decline", "a fresh veto binds even after approval")
	assert_eq(store.answer(5, 0, "a").decision_id, "shop-002", "fresh veto provenance")
	store.shop_rulings(5, 0, ["a"], [], {"action": "skip", "rulings": [
		{"option_index": 0, "verdict": "approve"}]}, "shop-003", "skip")
	assert_eq(store.answer(5, 0, "a").verdict, "approve", "new explicit approval replaces decline")
	assert_eq(store.answer(5, 0, "a").decision_id, "shop-003", "every fresh ruling records its decision")


func test_shop_duplicate_ids_share_action_precedence_and_one_decline():
	for act in ["buy", "pass", "lock", "skip"]:
		var store = TurnRulings.new()
		var result = store.shop_rulings(5, 0, ["a", "a", "b", "b"], ["a", "b"],
			{"action": act, "option_index": 0, "rulings": [
				{"option_index": 0, "verdict": "approve"}, {"option_index": 1, "verdict": "decline"},
				{"option_index": 2, "verdict": "decline"}, {"option_index": 3, "verdict": "approve"}]}, "run-001", act)
		assert_eq(result.declined, [2] if act == "buy" else ([0, 2] if act == "pass" else [1, 2]), "one pass per id; action wins")
		assert_eq(store.answer(5, 0, "a").verdict, "approve" if act == "buy" else "decline", "conflicting copies decline unless buy wins")


func test_shop_partial_duplicate_invalid_rulings_default_only_review_ids():
	var store = TurnRulings.new()
	var result = store.shop_rulings(5, 0, ["review", "ordinary", "good", "bad"], ["review"],
		{"action": "reroll", "rulings": [
			{"option_index": 0, "verdict": "approve"}, {"option_index": 0, "verdict": "decline"},
			{"option_index": 2, "verdict": "approve"}, {"option_index": 3, "verdict": "bad"},
			{"option_index": 99, "verdict": "decline"}]}, "run-001", "reroll")
	assert_eq(result.missing, 3, "duplicate, absent and bad verdict count as missing")
	assert_eq(result.declined, [0], "only missing review id is auto-declined")
	assert_eq(store.answer(5, 0, "good").verdict, "approve", "valid approval retained")
	assert_true(store.answer(5, 0, "ordinary").empty(), "ordinary unruled stays with rules")
	assert_true(store.answer(5, 0, "bad").empty(), "bad verdict on ordinary gives no verdict")


func test_shop_buy_decline_contradiction_and_lock_decline_are_binding():
	for act in ["buy", "lock"]:
		var store = TurnRulings.new()
		var result = store.shop_rulings(5, 0, ["a"], ["a"], {"action": act, "option_index": 0,
			"rulings": [{"option_index": 0, "verdict": "decline"}]}, "run-001", act)
		assert_eq(result.missing, 0, "contradiction isn't missing")
		assert_eq(result.declined, [] if act == "buy" else [0], "lock does not override decline")
		assert_eq(store.answer(5, 0, "a").verdict, "approve" if act == "buy" else "decline", "buy wins; lock follows verdict")


func test_shop_fully_answered_board_cannot_ask_again_this_turn():
	for verdicts in [["approve", "approve", "approve"], ["approve", "approve", "decline"], ["decline", "decline", "decline"]]:
		var store = TurnRulings.new()
		var rulings = []
		var entries = []
		for i in 3:
			var id = ["a", "b", "c"][i]
			rulings.append({"option_index": i, "verdict": verdicts[i]})
			entries.append({"node": id, "id": id, "kind": "item", "price": 100, "score": 20.0})
		store.shop_rulings(5, 0, ["a", "b", "c"], ["a"],
			{"action": "reroll", "rulings": rulings}, "run-001", "reroll")
		var ruled = store.for_player(5, 0)
		var board = DecisionClient.shop_options(entries, 400, ruled)
		assert_eq(board.ids.size(), 0 if verdicts[0] == "decline" else (2 if verdicts[2] == "decline" else 3), "declines filtered; approvals visible")
		assert_eq(DecisionClient.should_ask(board.scores, board.affordable, {}, board.ids,
			["a"], 6.0, 400, board.prices, 0, ruled), "", "fully ruled board suppresses tie, big and pivot triggers")
		board = DecisionClient.shop_options([
			{"node": "d", "id": "d", "kind": "item", "price": 20, "score": 10.0},
			{"node": "e", "id": "e", "kind": "item", "price": 20, "score": 9.0}], 400, ruled)
		assert_eq(DecisionClient.should_ask(board.scores, board.affordable, {}, board.ids,
			[], 6.0, 400, board.prices, 1, ruled), "ask", "fresh unruled reroll board still asks within visit budget")


func test_crate_review_fallback_recycles_without_recording_a_verdict():
	var store = TurnRulings.new()
	for score in [-5.0, 0.0, 50.0]:
		assert_eq(TurnRulings.crate_fallback("review", ["review"], score), "recycle", "review requires an answer even at high score")
		assert_eq(TurnRulings.crate_fallback("ordinary", ["review"], score), "recycle" if score < 0.0 else "take", "ordinary score fallback")
	assert_true(store.answer(5, 0, "review").empty(), "fallback leaves later review possible")


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
