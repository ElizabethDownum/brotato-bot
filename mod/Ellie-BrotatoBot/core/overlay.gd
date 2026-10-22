extends Reference
# The on-screen status block's text. Pure logic (static funcs) so it runs in
# the headless test project; BotRuntime builds the input dict each frame and
# shows text() on its status Label (CanvasLayer 100, processes while paused).
# No class_name -- callers preload this script.
#
# lines(s) takes a Dictionary (missing keys fall back to idle defaults):
#   bot_state             "idle" | "acting" | "deciding" | "halted" | "complete"
#   status_text           BotRuntime.status_text ("" when none)
#   deciding_deadline_ms  decide()'s OS.get_ticks_msec() deadline (0 when none)
#   now_ms                OS.get_ticks_msec() now
#   outcome               complete()'s outcome ("win" | "death")
#   plan_id, target       plan in effect and target challenge ("" when none)
#   last_decision         {kind, id, source, response} ({} when none)
#   focus_ok, plan_present  Guards.focus_setting_ok / Guards.plan_present
# and returns four lines (any may be ""):
#   1. status_text, else "RUN COMPLETE: <outcome>" when complete, else
#      "BOT <bot_state>"; while deciding with a deadline, " <seconds left>s"
#      is appended (rounded up, never negative)
#   2. "plan <plan_id> | target <target or none>" ("-" for an unknown plan)
#   3. "<kind>: <action> #<option_index> via <source>" for the last decision
#      ("#<option_index>" only when the response has one, "-" for no action)
#   4. warnings joined by " | ": "focus: pause_on_focus_lost", "no plan.json"


static func lines(s: Dictionary) -> Array:
	return [_status_line(s), _plan_line(s), _decision_line(s.get("last_decision", {})),
		_warning_line(s)]


static func text(s: Dictionary) -> String:
	return PoolStringArray(lines(s)).join("\n")


# The block is shown while AI visuals are on, the bot is doing anything, or an
# F9 export's status window is open (the export works with the bot off).
static func visible(ai_visuals, bot_state, export_active = false) -> bool:
	return bool(ai_visuals) or str(bot_state) != "idle" or bool(export_active)


static func _status_line(s):
	var state = str(s.get("bot_state", "idle"))
	var line = str(s.get("status_text", ""))
	if line == "":
		if state == "complete":
			line = "RUN COMPLETE: " + str(s.get("outcome", ""))
		else:
			line = "BOT " + state
	var deadline = int(s.get("deciding_deadline_ms", 0))
	if state == "deciding" and deadline > 0:
		var left_ms = max(0, deadline - int(s.get("now_ms", 0)))
		line += " %ds" % int(ceil(left_ms / 1000.0))
	return line


static func _plan_line(s):
	var plan_id = str(s.get("plan_id", ""))
	var target = str(s.get("target", ""))
	return "plan %s | target %s" % [plan_id if plan_id != "" else "-",
		target if target != "" else "none"]


static func _decision_line(d):
	if typeof(d) != TYPE_DICTIONARY or d.empty():
		return ""
	var action = "-"
	var index = ""
	var r = d.get("response")
	if typeof(r) == TYPE_DICTIONARY:
		if r.get("action") != null:
			action = str(r.action)
		var oi = r.get("option_index")
		if typeof(oi) == TYPE_INT or typeof(oi) == TYPE_REAL:
			index = " #%d" % int(oi)
	return "%s: %s%s via %s" % [str(d.get("kind", "")), action, index, str(d.get("source", ""))]


static func _warning_line(s):
	var w = []
	if not s.get("focus_ok", true):
		w.append("focus: pause_on_focus_lost")
	if not s.get("plan_present", true):
		w.append("no plan.json")
	return PoolStringArray(w).join(" | ")
