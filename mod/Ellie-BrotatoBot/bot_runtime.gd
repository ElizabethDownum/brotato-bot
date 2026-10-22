extends Node
# Run-scoped bot state shared by the mod's scripts. One instance lives at
# /root/BotRuntime, added by mod_main.gd. Look it up with
# get_node_or_null("/root/BotRuntime") from a node in the tree, or with
# BotRuntime.instance() (preloaded) from anywhere.
#
#   recorder       RunRecorder for the current run, or null before the first run
#   config         BotConfig.load_from(BotConfig.DEFAULT_PATH), read at _ready
#   run_id         the open run's id ("" when none)
#   bot_state      "idle" | "acting" | "deciding" | "halted" | "complete"
#   last_decision  the last decide() record {kind, id, source, response}
#                  ({} when none); callers read .id for decision_applied
#   status_text    one-line status shown top-left ("" hides it); Task 10's
#                  overlay replaces this label
#   focus_warned_run_id  run_id the pause_on_focus_lost warning was recorded for
#   seq            state exports written this run (reset at run start); the
#                  next export file is <run_id>-<seq+1:03>.json
#   recent_snapshots  the last RECENT_MAX snapshot dicts ai_telemetry recorded
#                  (cleared at run start); read by StateExport.collect
#   target_fired   the target challenge completed during this run (reset at
#                  run start); main.gd checkpoints at the next wave end
#   checkpoint_done  that checkpoint has been handled this run (reset at run start)

const BotConfig = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_config.gd")
const Guards = preload("res://mods-unpacked/Ellie-BrotatoBot/core/guards.gd")
const StateExport = preload("res://mods-unpacked/Ellie-BrotatoBot/core/state_export.gd")
const DecisionClient = preload("res://mods-unpacked/Ellie-BrotatoBot/core/decision_client.gd")
const BotPaths = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_paths.gd")
const PlanFile = preload("res://mods-unpacked/Ellie-BrotatoBot/core/plan_file.gd")
const Checkpoint = preload("res://mods-unpacked/Ellie-BrotatoBot/core/checkpoint.gd")

const NODE_NAME = "BotRuntime"
const RECENT_MAX = 10

var recorder = null
var config = {}
var run_id = ""
var bot_state = "idle"
var last_decision = {}
var status_text = ""
var focus_warned_run_id = null
var seq = 0
var recent_snapshots = []
var target_fired = false
var checkpoint_done = false

# Export hotkey (config.export_hotkey, default "F9"): handled here because this
# node keeps processing while the tree is paused, so the advisor export works
# from the ESC pause menu too. The overlay shows "Exported: <path>" for
# EXPORT_STATUS_MS, then the previous status comes back unless something else
# (e.g. a halt) replaced it meanwhile.
const EXPORT_STATUS_MS = 5000
var _export_scancode = 0
var _export_hotkey_warned = false
var _export_status_text = ""
var _export_status_until_ms = 0
var _status_before_export = ""

var _status_label = null
var _move_scancodes = null


func _init():
	pause_mode = PAUSE_MODE_PROCESS


func _ready():
	config = BotConfig.load_from(BotConfig.DEFAULT_PATH)
	var layer = CanvasLayer.new()
	layer.layer = 100
	layer.pause_mode = PAUSE_MODE_PROCESS
	add_child(layer)
	_status_label = Label.new()
	_status_label.set_name("StatusLabel")
	_status_label.rect_position = Vector2(8, 8)
	layer.add_child(_status_label)
	set_status(status_text)
	# Added deferred by mod_main, so the game autoloads are already in the tree.
	var challenges = get_node_or_null("/root/ChallengeService")
	if challenges != null:
		var _e = challenges.connect("challenge_completed", self, "_on_challenge_completed")
	else:
		push_warning("BrotatoBot: /root/ChallengeService missing; no challenge events")


# ChallengeService emits challenge_completed(chal_data) once per challenge,
# the first time it completes on this profile. Records a challenge event
# {id, is_target} while a run file is open. The first completion matching the
# target (PlanFile.target_id: the plan file's target_challenge, else the
# config's) sets target_fired; main.gd then checkpoints at the next wave end.
# "TARGET: <id> DONE" is shown only while the bot plays (acting/deciding), so a
# HALTED or RUN COMPLETE status stays. If it fires while deciding, decide()
# puts its pre-decision status back afterwards and the TARGET text goes
# (accepted).
func _on_challenge_completed(chal):
	var id = ""
	if chal != null and "my_id" in chal:
		id = str(chal.my_id)
	var target = PlanFile.target_id(PlanFile.load_cached(PlanFile.DEFAULT_PATH), config)
	var is_target = Checkpoint.is_target(id, target)
	if recorder != null and recorder.is_open():
		recorder.event("challenge", {"id": id, "is_target": is_target})
	if is_target and not target_fired:
		target_fired = true
		if bot_state == "acting" or bot_state == "deciding":
			set_status("TARGET: %s DONE" % id)


# The target checkpoint (coroutine). main.gd starts it at a wave end once
# Checkpoint.due(...) holds and the bot is acting; it lives here, on the
# persistent autoload, because main is freed by the scene change. Marks the
# checkpoint done, then:
#   - no live sidecar (decide()'s contract): no request, no pause; checkpoint
#     {applied: "skip", reason: "no_sidecar"}
#   - else decide("checkpoint", []), mapped by Checkpoint.wanted(response,
#     last_decision.source, bot_state == "acting"): a revise_plan answer is
#     applied with apply_plan_patch for player 0's character (a failed save is
#     skip / "patch_not_applied"); interrupted, invalid, busy and halted are
#     skips with that reason; no answer is "timeout".
# Records checkpoint {id, action, applied, reason} (reason "" when none).
func checkpoint():
	checkpoint_done = true
	if not DecisionClient.sidecar_alive(BotPaths.ROOT, OS.get_unix_time()):
		_record_checkpoint({"id": "", "action": null, "applied": "skip", "reason": "no_sidecar"})
		return
	var r = yield(decide("checkpoint", []), "completed")
	var out = Checkpoint.wanted(r, last_decision.get("source", ""), bot_state == "acting")
	if out.applied == "revise_plan":
		var ch = RunData.get_player_character(0) if RunData.get_player_count() > 0 else null
		if not apply_plan_patch(ch.my_id if ch != null else "", r.plan_patch):
			out = {"applied": "skip", "reason": "patch_not_applied"}
	_record_checkpoint({"id": last_decision.get("id", ""),
		"action": r.get("action") if r != null else null,
		"applied": out.applied, "reason": out.reason})


func _record_checkpoint(data):
	if recorder != null and recorder.is_open():
		recorder.event("checkpoint", data)


# Applies a revise_plan response's plan_patch to plan.json for character_id
# (PlanFile.apply_patch; a newly created file gets plan_id
# "sidecar-<last decision id>"). Shared by the shop and the wave-end
# checkpoint. Returns true when the patched plan was saved.
func apply_plan_patch(character_id, patch) -> bool:
	if str(character_id) == "" or typeof(patch) != TYPE_DICTIONARY:
		return false
	return PlanFile.apply_patch(PlanFile.DEFAULT_PATH, str(character_id), patch,
		"sidecar-" + str(last_decision.get("id", ""))) == OK


# Read-only: never shops, steers or changes bot_state. Any profile, bot on or off.
func _input(event):
	if event is InputEventKey and event.pressed and not event.echo \
			and event.scancode == _export_hotkey_scancode():
		_export_advise()
		get_tree().set_input_as_handled()


func _process(_delta):
	_restore_status_after_export()


# Scancode for config.export_hotkey. Cached only once resolved from a loaded
# config; before that (or for an unknown key name) F9 is used for this press
# and the lookup runs again next time.
func _export_hotkey_scancode() -> int:
	if _export_scancode != 0:
		return _export_scancode
	if config.empty():
		return KEY_F9
	var key_name = str(config.get("export_hotkey", "F9"))
	var sc = OS.find_scancode_from_string(key_name)
	if sc == 0:
		if not _export_hotkey_warned:
			_export_hotkey_warned = true
			push_warning("BrotatoBot: unknown export_hotkey '%s'; using F9" % key_name)
		return KEY_F9
	_export_scancode = sc
	return sc


func _export_advise():
	var path = export_state("advise")
	var msg = "Export failed (see log)"
	if path != "":
		msg = "Exported: " + ProjectSettings.globalize_path(path)
	if bot_state == "deciding":
		# decide() puts its own pre-decision status back when it ends; a
		# timed restore here would bring "DECIDING: ..." back afterwards.
		_export_status_until_ms = 0
		set_status(msg)
		return
	if _export_status_until_ms == 0:
		_status_before_export = status_text
	_export_status_text = msg
	_export_status_until_ms = OS.get_ticks_msec() + EXPORT_STATUS_MS
	set_status(msg)


func _restore_status_after_export():
	if _export_status_until_ms == 0 or OS.get_ticks_msec() < _export_status_until_ms:
		return
	_export_status_until_ms = 0
	if status_text == _export_status_text:
		set_status(_status_before_export)


func set_status(text: String):
	status_text = text
	if _status_label != null:
		_status_label.text = text
		_status_label.visible = text != ""


# The single gate for every bot action (movement, shop, level-up picks): the
# bot is "acting" (or "deciding": waiting on the sidecar inside decide(), with
# the tree paused, which must not switch the shop or level-up gates off) and
# the game is on the bot profile. Acting on the wrong
# profile halts the bot ("wrong profile") and returns false. Fails closed when
# ProgressData is missing.
func may_act() -> bool:
	if bot_state != "acting" and bot_state != "deciding":
		return false
	var progress = get_node_or_null("/root/ProgressData")
	if progress == null:
		return false
	if not Guards.profile_ok(progress.current_profile_id, config):
		halt("wrong profile")
		return false
	return true


# Move-key scancodes for Guards.is_human_move, built from the InputMap once.
func move_scancodes() -> Array:
	if _move_scancodes == null:
		_move_scancodes = Guards.default_move_scancodes()
	return _move_scancodes


# Back at the main menu: the bot is off for the next run (Continue loads the
# shop directly, so enablement must not carry over). Not a halt: no event.
func reset_for_menu():
	bot_state = "idle"
	_disable_flags()
	set_status("")


# Stops the bot at once: state "halted", both bot flags off on
# /root/AutobattlerOptions (persisted), a halt event, and the HALTED status.
# A later Shift+Space goes through the enable guards again.
func halt(reason: String):
	bot_state = "halted"
	_disable_flags()
	if recorder != null:
		recorder.event("halt", {"reason": reason})
	set_status("HALTED: " + reason)


# The run ended (player 0 died, or the run was won) while the bot was playing:
# state "complete", both bot flags off (persisted), a complete event and the
# RUN COMPLETE status. outcome is "win" or "death" (anything else is warned
# about and treated as "death"; main.gd maps its "won" with
# Guards.normalize_outcome). The run's end line is main.gd's job; this
# never writes a second one. may_act() is false from here on, so neither the
# post-run shop nor movement acts.
func complete(outcome: String, extra: Dictionary):
	if not outcome in ["win", "death"]:
		push_warning("BrotatoBot: complete() got outcome '%s'; using death" % outcome)
		outcome = "death"
	bot_state = "complete"
	_disable_flags()
	if recorder != null:
		recorder.event("complete", {"outcome": outcome, "wave": RunData.current_wave, "extra": extra})
	set_status("RUN COMPLETE: " + outcome)


# Turns enable_autobattler and enable_autoshop off on /root/AutobattlerOptions,
# tells its listeners and persists the change. Shared by halt, complete and
# reset_for_menu.
func _disable_flags():
	var options = get_node_or_null("/root/AutobattlerOptions")
	if options == null:
		return
	options.enable_autobattler = false
	options.enable_autoshop = false
	options.emit_signal("setting_changed", options.ENABLE_AUTOBATTLER_OPTION_NAME, false, options.MOD_NAME)
	options.emit_signal("setting_changed", options.ENABLE_AUTOSHOP_OPTION_NAME, false, options.MOD_NAME)
	options.save_configs()


# A new run file was opened: export numbering, snapshot history and the
# target checkpoint restart.
func on_run_started():
	seq = 0
	recent_snapshots = []
	target_fired = false
	checkpoint_done = false


# Called by ai_telemetry next to each recorder snapshot; keeps the last RECENT_MAX.
func push_snapshot(snap: Dictionary):
	recent_snapshots.append(snap.duplicate(true))
	while recent_snapshots.size() > RECENT_MAX:
		recent_snapshots.pop_front()


# Writes user://brotato-bot/state/<run_id>-<seq:03>.json (or
# norun-<YYYYMMDD-HHMMSS>-<seq:03>.json when no run is open) for player 0 and returns the path ("" when it could not be
# written). Read-only towards the game and the bot: it never shops, picks,
# steers or changes bot_state. Records an "export" event on an open recorder
# (the export kind as "export_kind": the recorder overwrites a "kind" key).
func export_state(kind: String) -> String:
	seq += 1
	var rid = run_id if run_id != "" else StateExport.NORUN_ID
	var clock = OS.get_datetime()
	var parts = StateExport.collect(0)
	var data = StateExport.serialize(parts, {"kind": kind, "run_id": rid, "seq": seq, "clock": clock})
	var path = StateExport.write(StateExport.STATE_DIR, rid, seq, data, clock)
	if path == "":
		return ""
	if recorder != null and recorder.is_open():
		recorder.event("export", {"export_kind": kind, "path": path, "seq": seq})
	return path


# Asks the sidecar (coroutine; callers `yield(rt.decide(...), "completed")`).
# Always yields at least once, so the caller's yield is safe on every path.
#   0. Non-reentrant: while another decide() is waiting (bot_state
#      "deciding"), returns null after one idle frame with a decision event of
#      source "busy" (id "", no export, no request).
#   1. Guard: bot_state must be "acting", else returns null at once (after one
#      idle frame), with no request and no event.
#   2. export_state(kind) writes state/<id>.json; the request id is
#      "<run_id>-<seq:03>" for that same seq, so state and request match.
#      A leftover responses/<id>.json is deleted before the request is written.
#   3. Writes requests/<id>.json {kind, run_id, seq, state_path, options,
#      deadline_ms (epoch ms)} via DecisionClient.
#   4. bot_state "deciding", status "DECIDING: <kind>", tree paused; polls
#      responses/ every POLL_S (timers process while paused) until a response
#      or the timeout (config checkpoint_timeout_ms for "checkpoint", else
#      request_timeout_ms), or until bot_state leaves "deciding" (a halt),
#      or until something else unpaused the tree that decide() paused (the
#      pause menu's ESC: a human intervened, and the human wins -- no
#      re-pause, source "interrupted", the rules decide).
#   5. Unpauses only if the tree was not already paused; unless bot_state
#      became halted/complete meanwhile, returns it to "acting" and restores
#      the status shown before decide() (an F9 export meanwhile included).
#   Callers ask only while DecisionClient.sidecar_alive(...) is true.
#   6. Records a decision event {request_kind, id, source, response} with source
#      "haiku" (valid response), "invalid" (a response that failed
#      validate_response; its file is deleted all the same), "interrupted"
#      (human unpause, step 4), "busy" (step 0) or "timeout" (also used when
#      the export or request write failed, or on a halt), stores
#      {kind, id, source, response} in last_decision, and returns the
#      response or null.
# The caller records what it actually did as a decision_applied event.
const POLL_S = 0.25

func decide(kind: String, options: Array):
	if bot_state == "deciding":
		yield(get_tree(), "idle_frame")
		_record_decision(kind, "", "busy", null)
		return null
	if bot_state != "acting":
		yield(get_tree(), "idle_frame")
		return null
	var timeout_key = "checkpoint_timeout_ms" if kind == "checkpoint" else "request_timeout_ms"
	var timeout_ms = int(config.get(timeout_key, 120000 if kind == "checkpoint" else 45000))
	var state_path = export_state(kind)
	var rid = run_id if run_id != "" else StateExport.NORUN_ID
	var client = DecisionClient.new(BotPaths.ROOT)
	var id = ""
	if state_path != "":
		client.discard_response(DecisionClient.request_id(rid, seq))
		id = client.write_request({
			"kind": kind,
			"run_id": rid,
			"seq": seq,
			"state_path": state_path,
			"options": options,
			"deadline_ms": OS.get_system_time_msecs() + timeout_ms,
		})
	if id == "":
		yield(get_tree(), "idle_frame")
		_record_decision(kind, DecisionClient.request_id(rid, seq), "timeout", null)
		return null
	# The status to put back afterwards. During an F9 export's 5 s window that
	# is the status the export will restore, not the "Exported: ..." text;
	# the export's own timed restore is cancelled.
	var prev_status = status_text
	if _export_status_until_ms != 0:
		if status_text == _export_status_text:
			prev_status = _status_before_export
		_export_status_until_ms = 0
	var status = "DECIDING: " + kind
	var was_paused = get_tree().paused
	bot_state = "deciding"
	set_status(status)
	get_tree().paused = true
	var deadline = OS.get_ticks_msec() + timeout_ms
	var response = null
	var interrupted = false
	while true:
		yield(get_tree().create_timer(POLL_S, true), "timeout")
		if not was_paused and not get_tree().paused:
			interrupted = true   # a human unpaused (pause menu): stop asking
			break
		response = client.poll_response(id)
		if response != null or OS.get_ticks_msec() >= deadline:
			break
		if bot_state != "deciding":
			break   # halted (e.g. wrong profile) or completed meanwhile: stop waiting
	if not was_paused:
		get_tree().paused = false
	# Status invariant: unless the bot was halted or completed meanwhile (their
	# status stays), the status is again what it was before decide() started.
	if bot_state == "deciding":
		bot_state = "acting"
		set_status(prev_status)
	var source = "interrupted" if interrupted else "timeout"
	if response != null:
		if DecisionClient.validate_response(response):
			source = "haiku"
		else:
			source = "invalid"
	_record_decision(kind, id, source, response)
	return response if source == "haiku" else null


# The recorder writes the event name into the line's "kind" (overwriting a data
# key of that name), so the request kind is logged as "request_kind".
func _record_decision(kind, id, source, response):
	last_decision = {"kind": kind, "id": id, "source": source, "response": response}
	if recorder != null and recorder.is_open():
		recorder.event("decision", {"request_kind": kind, "id": id, "source": source,
			"response": response.duplicate(true) if typeof(response) == TYPE_DICTIONARY else response})


# Game quit with a run still open: close the file with an end line.
func _exit_tree():
	if recorder != null and recorder.is_open():
		recorder.end_run({"outcome": "quit", "wave": null, "hp": null, "gold": null})
		run_id = ""


static func instance():
	var tree = Engine.get_main_loop()
	if tree == null or not (tree is SceneTree):
		return null
	return tree.root.get_node_or_null(NODE_NAME)
