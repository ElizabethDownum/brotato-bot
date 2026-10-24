extends "res://mod/tests/test_base.gd"

const DecisionClient = preload("res://mod/Ellie-BrotatoBot/core/decision_client.gd")

const CFG = {"ask_tie_margin": 3.0, "ask_floor": 8.0}


# A fresh scratch root under the test project's user dir.
func _make_root(name):
	var root = "user://brotato-bot/test-%s-%d" % [name, OS.get_ticks_usec()]
	if Directory.new().make_dir_recursive(root) != OK:
		failures.append("could not create scratch root %s" % root)
	return root


# Removes root and everything under it (root/requests/*, root/responses/*).
func _remove_tree(path):
	var d = Directory.new()
	if d.open(path) != OK:
		return
	d.list_dir_begin(true, true)
	var f = d.get_next()
	while f != "":
		var child = path.plus_file(f)
		if d.current_is_dir():
			_remove_tree(child)
		else:
			d.remove(child)
		f = d.get_next()
	d.list_dir_end()
	d.remove(path)


func _write(path, text):
	Directory.new().make_dir_recursive(path.get_base_dir())
	var f = File.new()
	if f.open(path, File.WRITE) != OK:
		failures.append("cannot write %s" % path)
		return
	f.store_string(text)
	f.close()


func _list(dir_path):
	var out = []
	var d = Directory.new()
	if d.open(dir_path) != OK:
		return out
	d.list_dir_begin(true, true)
	var f = d.get_next()
	while f != "":
		out.append(f)
		f = d.get_next()
	d.list_dir_end()
	out.sort()
	return out


func _req(seq):
	return {"kind": "shop", "run_id": "test-run", "seq": seq,
		"state_path": "user://brotato-bot/state/test-run-001.json",
		"options": [{"index": 0, "id": "item_anvil", "kind": "item", "price": 40, "score": 10.0}],
		"deadline_ms": 1234567890123}


func test_should_ask_on_tie_and_floor():
	assert_eq(DecisionClient.should_ask([10.0, 8.5], [0, 1], CFG), "ask", "tie within margin")
	assert_eq(DecisionClient.should_ask([20.0, 5.0], [0, 1], CFG), "", "clear winner above floor")
	assert_eq(DecisionClient.should_ask([6.0, 2.0], [0, 1], CFG), "ask", "best below floor")
	assert_eq(DecisionClient.should_ask([10.0, 8.5], [0], CFG), "", "one affordable")
	assert_eq(DecisionClient.should_ask([10.0, 8.5, 30.0], [0, 1], CFG), "ask",
		"unaffordable option ignored")
	assert_eq(DecisionClient.should_ask([10.0, 8.5], [0, 1], {}), "ask", "defaults when keys missing")


# Shop mode: min_buy given. Args after cfg: ids, ask_on, min_buy, gold, prices, asked.
const SHOP = {"ask_tie_margin": 3.0, "ask_floor": 6.0, "ask_gold_floor": 200,
	"ask_big_share": 0.25, "ask_per_visit": 2}


func _shop(scores, affordable, ids, ask_on, gold, prices, asked = 0, cfg = SHOP):
	return DecisionClient.should_ask(scores, affordable, cfg, ids, ask_on, 6.0, gold, prices, asked)


func test_shop_dead_board_never_asks():
	assert_eq(_shop([5.0, 5.5], [0, 1], ["a", "b"], [], 50, [10, 10]), "", "all below min_buy")
	assert_eq(_shop([30.0, 29.0], [], ["a", "b"], [], 50, [90, 90]), "", "nothing affordable")
	assert_eq(_shop([30.0, 29.0], [0, 1], ["a", "b"], [], 50, [10, 10]), "ask", "same board with scores up is a tie")


func test_shop_dead_board_beats_pivot():
	assert_eq(_shop([5.0, 40.0], [0], ["a", "goal"], ["goal"], 50, [10, 90]), "",
		"goal offered but unaffordable, the rest below min_buy")
	assert_eq(_shop([30.0, 40.0], [], ["a", "goal"], ["goal"], 20, [90, 90]), "", "nothing affordable")
	assert_eq(_shop([7.0, 40.0], [0], ["a", "goal"], ["goal"], 50, [10, 90]), "pivot",
		"goal unaffordable but another option reaches min_buy")
	assert_eq(DecisionClient.should_ask([1.0, 2.0], [0, 1], CFG, ["a", "goal"], ["goal"]), "pivot",
		"level-up keeps pivoting below the floor")


func test_shop_tie_needs_floor_and_margin():
	assert_eq(_shop([10.0, 8.5], [0, 1], ["a", "b"], [], 50, [10, 10]), "ask", "tie above floor")
	assert_eq(_shop([10.0, 5.0], [0, 1], ["a", "b"], [], 50, [10, 10]), "", "clear winner")
	assert_eq(_shop([10.0, 5.0, 30.0], [0, 1], ["a", "b", "c"], [], 50, [10, 10, 99]), "", "unaffordable ignored")
	assert_eq(_shop([6.0, 4.0], [0, 1], ["a", "b"], [], 50, [10, 10]), "ask", "best at the floor and within the margin")
	assert_eq(_shop([7.0], [0], ["a"], [], 50, [10]), "", "one affordable, small purchase")


func test_shop_pivot_on_every_board_but_capped():
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "goal"], ["goal"], 50, [10, 10], 1), "pivot", "second board still pivots")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "goal"], ["goal"], 50, [10, 10], 2), "", "ask_per_visit reached")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "b"], [], 50, [10, 10], 0, {}), "", "defaults when keys missing")


func test_shop_big_purchase():
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "b"], [], 400, [100, 10]), "ask", "100 of 400 gold is a quarter")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "b"], [], 400, [99, 10]), "", "just under a quarter")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "b"], [], 199, [60, 10]), "", "below the gold floor")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "goal"], ["goal"], 400, [100, 10]), "pivot", "goal on board pivots first")
	assert_eq(_shop([20.0, 5.0], [0, 1], ["a", "b"], [], 400, [10, 100]), "", "the big one is not the best option")


func test_should_ask_on_plan_ask_list():
	assert_eq(DecisionClient.should_ask([20.0, 5.0], [0, 1], CFG, ["anvil", "coupon"], ["anvil"]),
		"pivot", "ask_on hit wins over a clear winner")
	assert_eq(DecisionClient.should_ask([20.0, 5.0], [0, 1], CFG, ["anvil", "coupon"], ["x"]),
		"", "no ask_on hit")


func test_write_request_is_atomic_and_named():
	var root = _make_root("decision-write")
	var client = DecisionClient.new(root)
	var id = client.write_request(_req(1))
	var re = RegEx.new()
	re.compile("^test-run-001$")
	assert_true(re.search(id) != null, "id format: %s" % id)
	var path = root.plus_file("requests").plus_file("test-run-001.json")
	assert_true(File.new().file_exists(path), "request file at %s" % path)
	assert_eq(_list(root.plus_file("requests")), ["test-run-001.json"], "no .tmp left")
	var f = File.new()
	if f.open(path, File.READ) == OK:
		var parsed = JSON.parse(f.get_as_text())
		f.close()
		assert_eq(typeof(parsed.result), TYPE_DICTIONARY, "request is a JSON object")
		if typeof(parsed.result) == TYPE_DICTIONARY:
			var r = parsed.result
			for k in ["id", "kind", "run_id", "seq", "state_path", "options", "deadline_ms"]:
				assert_true(r.has(k), "request has %s" % k)
			assert_eq(r.get("id"), "test-run-001", "id in body")
			assert_eq(r.get("kind"), "shop", "kind")
	_remove_tree(root)


func test_poll_returns_and_deletes_response():
	var root = _make_root("decision-poll")
	var client = DecisionClient.new(root)
	assert_eq(typeof(client.poll_response("test-run-001")), TYPE_NIL, "nothing yet: null")
	var path = root.plus_file("responses").plus_file("test-run-001.json")
	_write(path, '{"action":"buy","option_index":0,"confidence":0.9,"rationale":"test","tags":[]}')
	var r = client.poll_response("test-run-001")
	assert_eq(typeof(r), TYPE_DICTIONARY, "parsed response")
	if typeof(r) == TYPE_DICTIONARY:
		assert_eq(r.get("action"), "buy", "action")
	assert_false(File.new().file_exists(path), "response deleted")
	_write(path, "{not json")
	var bad = client.poll_response("test-run-001")
	assert_eq(typeof(bad), TYPE_DICTIONARY, "unparseable response gives {}")
	if typeof(bad) == TYPE_DICTIONARY:
		assert_eq(bad.size(), 0, "{} is empty")
		assert_false(DecisionClient.validate_response(bad), "{} is invalid")
	assert_false(File.new().file_exists(path), "unparseable response deleted")
	_remove_tree(root)


func test_stale_response_is_ignored():
	var root = _make_root("decision-stale")
	var client = DecisionClient.new(root)
	var stale = root.plus_file("responses").plus_file("other-id.json")
	_write(stale, '{"action":"skip","confidence":0.5}')
	assert_eq(typeof(client.poll_response("test-run-001")), TYPE_NIL, "stale file not returned")
	assert_false(File.new().file_exists(stale), "stale file deleted")
	_remove_tree(root)


func test_validate_response_rejects_bad_action():
	assert_true(DecisionClient.validate_response({"action": "buy", "option_index": 1, "confidence": 0.5}), "valid buy")
	assert_true(DecisionClient.validate_response({"action": "skip", "confidence": 1.0, "rationale": "r"}), "valid skip")
	assert_true(DecisionClient.validate_response(
		{"action": "revise_plan", "confidence": 0.7, "plan_patch": {"max_rerolls": 3}}), "valid revise_plan")
	assert_false(DecisionClient.validate_response({"action": "sell", "confidence": 0.5}), "unknown action")
	assert_false(DecisionClient.validate_response({"confidence": 0.5}), "missing action")
	assert_false(DecisionClient.validate_response({"action": "buy", "confidence": 0.5}), "buy without index")
	assert_false(DecisionClient.validate_response({"action": "pick", "option_index": -1, "confidence": 0.5}), "negative index")
	assert_false(DecisionClient.validate_response({"action": "skip", "confidence": 1.5}), "confidence > 1")
	assert_false(DecisionClient.validate_response({"action": "skip"}), "missing confidence")
	assert_false(DecisionClient.validate_response({"action": "skip", "confidence": "high"}), "confidence not a number")
	assert_false(DecisionClient.validate_response({"action": "skip", "confidence": 0.5, "rationale": 3}), "rationale not a string")
	assert_false(DecisionClient.validate_response({"action": "revise_plan", "confidence": 0.5}), "revise_plan without patch")
	assert_false(DecisionClient.validate_response(["buy"]), "not a dictionary")
	assert_false(DecisionClient.validate_response(null), "null")


func test_sidecar_alive_requires_fresh_file():
	var root = _make_root("decision-alive")
	var now = OS.get_unix_time()
	assert_false(DecisionClient.sidecar_alive(root, now), "missing file")
	_write(root.plus_file("sidecar.alive"), "")
	now = OS.get_unix_time()
	assert_true(DecisionClient.sidecar_alive(root, now), "just written")
	assert_false(DecisionClient.sidecar_alive(root, now + 60), "60 s later")
	assert_true(DecisionClient.sidecar_alive(root, now + 60, 120), "custom max age")
	_remove_tree(root)


func test_discard_response_removes_only_that_id():
	var root = _make_root("decision-discard")
	var client = DecisionClient.new(root)
	var mine = root.plus_file("responses").plus_file("test-run-001.json")
	var other = root.plus_file("responses").plus_file("test-run-002.json")
	_write(mine, '{"action":"skip","confidence":0.5}')
	_write(other, '{"action":"skip","confidence":0.5}')
	client.discard_response("test-run-001")
	assert_false(File.new().file_exists(mine), "leftover response removed")
	assert_true(File.new().file_exists(other), "other id untouched")
	client.discard_response("test-run-003")   # missing: no error
	_remove_tree(root)


func test_validate_response_coerces_float_index():
	var r = {"action": "pick", "option_index": 2.0, "confidence": 0.8}
	assert_true(DecisionClient.validate_response(r), "whole float index accepted")
	assert_eq(r.get("option_index"), 2, "coerced to int in place")
	assert_false(DecisionClient.validate_response({"action": "pick", "option_index": 1.5, "confidence": 0.8}),
		"fractional index rejected")
	var c = {"action": "skip", "confidence": 1}
	assert_true(DecisionClient.validate_response(c), "int confidence accepted")
	assert_eq(c.get("confidence"), 1.0, "confidence coerced to float")


func test_validate_pass_requires_a_nonnegative_whole_index():
	var r = {"action": "pass", "option_index": 1.0, "confidence": 0.8}
	assert_true(DecisionClient.validate_response(r), "pass accepted")
	assert_eq(r.get("option_index"), 1, "whole float coerced to int")
	assert_false(DecisionClient.validate_response({"action": "pass", "confidence": 0.8}),
		"pass needs a target")
	for index in [-1, 1.5, null, "1", true]:
		assert_false(DecisionClient.validate_response({"action": "pass", "option_index": index, "confidence": 0.8}),
			"invalid pass index: %s" % str(index))


func test_poll_returns_a_pass_response():
	var root = _make_root("decision-pass")
	var client = DecisionClient.new(root)
	var path = root.plus_file("responses").plus_file("test-run-001.json")
	_write(path, '{"action":"pass","option_index":0,"confidence":0.8}')
	var r = client.poll_response("test-run-001")
	assert_eq(r.get("action"), "pass", "pass survives file protocol")
	assert_true(DecisionClient.validate_response(r), "polled pass validates and normalizes")
	assert_eq(r.get("option_index"), 0, "selected option retained")
	assert_false(File.new().file_exists(path), "response consumed")
	_remove_tree(root)


func test_build_request_carries_screen_and_kind():
	var opts = [{"index": 0, "id": "item_anvil"}]
	var r = DecisionClient.build_request("pivot", "levelup", "run-a", 4, "user://s.json", opts, 99)
	assert_eq(r.get("kind"), "pivot", "kind stays pivot")
	assert_eq(r.get("screen"), "levelup", "screen says which screen")
	assert_eq(r.get("run_id"), "run-a", "run_id")
	assert_eq(r.get("seq"), 4, "seq")
	assert_eq(r.get("state_path"), "user://s.json", "state_path")
	assert_eq(r.get("options"), opts, "options")
	assert_eq(r.get("deadline_ms"), 99, "deadline_ms")
	var keys = r.keys()
	keys.sort()
	assert_eq(keys, ["deadline_ms", "kind", "options", "run_id", "screen", "seq", "state_path"], "exact fields")


func test_screen_for_kind():
	assert_eq(DecisionClient.SCREENS, ["shop", "levelup", "crate", "checkpoint"], "screens")
	var r = DecisionClient.build_request("checkpoint", "checkpoint", "r", 1, "p", [], 0)
	assert_eq(r.get("screen"), "checkpoint", "checkpoint screen")


func test_write_request_honours_an_explicit_id():
	var root = _make_root("decision-explicit-id")
	var client = DecisionClient.new(root)
	var req = _req(7)
	req["id"] = "norun-20261022-101500-007"
	var id = client.write_request(req)
	assert_eq(id, "norun-20261022-101500-007", "explicit id kept")
	assert_eq(_list(root.plus_file("requests")), ["norun-20261022-101500-007.json"], "file named by it")
	_remove_tree(root)


class DescriptionEffect:
	extends Resource
	var text_key = ""


func test_has_description_effect_on_resources_and_dictionaries():
	assert_false(DecisionClient.has_description_effect([]), "no effects")
	assert_false(DecisionClient.has_description_effect([null, {"key": "stat_max_hp", "value": 3}, {"text_key": ""}]), "plain stats")
	assert_true(DecisionClient.has_description_effect([{"key": "lose_hp_per_second", "value": 1, "text_key": "effect_lose_hp_per_second"}]), "unweighted description")
	assert_true(DecisionClient.has_description_effect([{"key": "stat_attack_speed", "value": 40, "text_key": "effect_stat_while_not_moving"}]), "weighted conditional still asks")
	var effect = DescriptionEffect.new()
	assert_false(DecisionClient.has_description_effect([effect]), "plain resource")
	effect.text_key = "effect_hp_start_next_wave"
	assert_true(DecisionClient.has_description_effect([null, effect]), "Resource property, like in-game Effect")


func test_crate_actions_need_no_option_index():
	for action in ["take", "recycle"]:
		assert_true(DecisionClient.validate_response({"action": action, "confidence": 0.8}), "crate action")
		assert_false(DecisionClient.validate_response({"action": action, "option_index": 0, "confidence": 0.8}), "no crate index")
	var options = [{"index": 0, "id": "item_weird_ghost", "kind": "item", "score": 1.0}]
	var r = DecisionClient.build_request("crate", "crate", "run-a", 5, "user://s.json", options, 99)
	assert_eq(r.screen, "crate", "crate screen")
	assert_eq(r.options, options, "one item, with score")
