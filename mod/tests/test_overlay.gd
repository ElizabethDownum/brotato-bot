extends "res://mod/tests/test_base.gd"

const Overlay = preload("res://mod/Ellie-BrotatoBot/core/overlay.gd")


# A status dict with every field at its idle default; tests override fields.
func _s(over = {}):
	var s = {
		"bot_state": "idle",
		"status_text": "",
		"deciding_deadline_ms": 0,
		"now_ms": 0,
		"outcome": "",
		"plan_id": "builtin",
		"target": "",
		"last_decision": {},
		"focus_ok": true,
		"plan_present": true,
	}
	for k in over:
		s[k] = over[k]
	return s


func _line(i, over = {}):
	return Overlay.lines(_s(over))[i]


func test_lines_always_returns_four_lines():
	assert_eq(Overlay.lines(_s()).size(), 4, "idle")
	assert_eq(Overlay.lines({}).size(), 4, "empty dict degrades to defaults")


func test_line1_is_bot_state_when_no_status():
	assert_eq(_line(0), "BOT idle", "idle")
	assert_eq(_line(0, {"bot_state": "acting"}), "BOT acting", "acting")


func test_line1_prefers_status_text():
	assert_eq(_line(0, {"bot_state": "halted", "status_text": "HALTED: wrong profile"}),
		"HALTED: wrong profile", "halt status")
	assert_eq(_line(0, {"bot_state": "acting", "status_text": "TARGET: chal_x DONE"}),
		"TARGET: chal_x DONE", "target status")


func test_line1_appends_seconds_left_while_deciding():
	var over = {"bot_state": "deciding", "status_text": "DECIDING: shop",
		"deciding_deadline_ms": 50000, "now_ms": 20000}
	assert_eq(_line(0, over), "DECIDING: shop 30s", "30 s left")
	over.now_ms = 20001
	assert_eq(_line(0, over), "DECIDING: shop 30s", "partial seconds round up")
	over.now_ms = 49999
	assert_eq(_line(0, over), "DECIDING: shop 1s", "last second")


func test_line1_seconds_left_never_negative():
	var over = {"bot_state": "deciding", "status_text": "DECIDING: shop",
		"deciding_deadline_ms": 50000, "now_ms": 60000}
	assert_eq(_line(0, over), "DECIDING: shop 0s", "past the deadline")


func test_line1_no_countdown_without_a_deadline_or_when_not_deciding():
	assert_eq(_line(0, {"bot_state": "deciding", "status_text": "DECIDING: shop"}),
		"DECIDING: shop", "no deadline yet")
	assert_eq(_line(0, {"bot_state": "acting", "deciding_deadline_ms": 50000, "now_ms": 0}),
		"BOT acting", "stale deadline ignored when not deciding")


func test_line1_run_complete_when_status_empty():
	assert_eq(_line(0, {"bot_state": "complete", "outcome": "win"}), "RUN COMPLETE: win", "win")
	assert_eq(_line(0, {"bot_state": "complete", "outcome": "death", "status_text": "Exported: x"}),
		"Exported: x", "status text still wins")


func test_line2_plan_and_target():
	assert_eq(_line(1, {"plan_id": "p7", "target": "chal_gatherer_1"}),
		"plan p7 | target chal_gatherer_1", "both")
	assert_eq(_line(1, {"plan_id": "builtin", "target": ""}), "plan builtin | target none", "no target")
	assert_eq(_line(1, {"plan_id": ""}), "plan - | target none", "unknown plan")


func test_line3_empty_without_a_decision():
	assert_eq(_line(2), "", "no decision yet")


func test_line3_formats_kind_action_index_source():
	var d = {"kind": "shop", "id": "r-003", "source": "haiku",
		"response": {"action": "buy", "option_index": 2}}
	assert_eq(_line(2, {"last_decision": d}), "shop: buy #2 via haiku", "with index")
	d.response = {"action": "reroll"}
	assert_eq(_line(2, {"last_decision": d}), "shop: reroll via haiku", "no option_index")
	d.response = {"action": "buy", "option_index": null}
	assert_eq(_line(2, {"last_decision": d}), "shop: buy via haiku", "null option_index")


func test_line3_dash_when_no_action():
	var d = {"kind": "checkpoint", "id": "r-004", "source": "timeout", "response": null}
	assert_eq(_line(2, {"last_decision": d}), "checkpoint: - via timeout", "null response")
	d.response = {"action": null}
	assert_eq(_line(2, {"last_decision": d}), "checkpoint: - via timeout", "null action")


func test_line3_index_is_an_integer():
	# JSON numbers arrive as floats.
	var d = {"kind": "level_up", "id": "r", "source": "haiku",
		"response": {"action": "pick", "option_index": 1.0}}
	assert_eq(_line(2, {"last_decision": d}), "level_up: pick #1 via haiku", "float index")


func test_line4_warnings():
	assert_eq(_line(3), "", "none")
	assert_eq(_line(3, {"focus_ok": false}), "focus: pause_on_focus_lost", "focus")
	assert_eq(_line(3, {"plan_present": false}), "no plan.json", "plan")
	assert_eq(_line(3, {"focus_ok": false, "plan_present": false}),
		"focus: pause_on_focus_lost | no plan.json", "both")


func test_text_joins_lines_with_newlines():
	var t = Overlay.text(_s({"bot_state": "acting", "plan_id": "p1", "target": "c1"}))
	assert_eq(t, "BOT acting\nplan p1 | target c1\n\n", "four lines")


func test_visible_when_idle_with_a_status():
	assert_true(Overlay.visible(false, "idle", "Exported: C:/x.json"), "idle + status")


func test_hidden_when_idle_without_status_or_visuals():
	assert_false(Overlay.visible(false, "idle", ""), "idle, no status, visuals off")


func test_visible_when_idle_with_ai_visuals():
	assert_true(Overlay.visible(true, "idle", ""), "visuals on")


func test_visible_when_acting_without_status():
	assert_true(Overlay.visible(false, "acting", ""), "acting")
