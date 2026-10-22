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
#   last_decision  the last sidecar decision record ({} when none)
#   status_text    one-line status shown top-left ("" hides it); Task 10's
#                  overlay replaces this label
#   focus_warned_run_id  run_id the pause_on_focus_lost warning was recorded for
#   seq            state exports written this run (reset at run start); the
#                  next export file is <run_id>-<seq+1:03>.json
#   recent_snapshots  the last RECENT_MAX snapshot dicts ai_telemetry recorded
#                  (cleared at run start); read by StateExport.collect

const BotConfig = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_config.gd")
const Guards = preload("res://mods-unpacked/Ellie-BrotatoBot/core/guards.gd")
const StateExport = preload("res://mods-unpacked/Ellie-BrotatoBot/core/state_export.gd")

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
# bot is "acting" and the game is on the bot profile. Acting on the wrong
# profile halts the bot ("wrong profile") and returns false. Fails closed when
# ProgressData is missing.
func may_act() -> bool:
	if bot_state != "acting":
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
	var options = get_node_or_null("/root/AutobattlerOptions")
	if options != null:
		options.enable_autobattler = false
		options.enable_autoshop = false
		options.emit_signal("setting_changed", options.ENABLE_AUTOBATTLER_OPTION_NAME, false, options.MOD_NAME)
		options.emit_signal("setting_changed", options.ENABLE_AUTOSHOP_OPTION_NAME, false, options.MOD_NAME)
		options.save_configs()
	set_status("")


# Stops the bot at once: state "halted", both bot flags off on
# /root/AutobattlerOptions (persisted), a halt event, and the HALTED status.
# A later Shift+Space goes through the enable guards again.
func halt(reason: String):
	bot_state = "halted"
	var options = get_node_or_null("/root/AutobattlerOptions")
	if options != null:
		options.enable_autobattler = false
		options.enable_autoshop = false
		options.emit_signal("setting_changed", options.ENABLE_AUTOBATTLER_OPTION_NAME, false, options.MOD_NAME)
		options.emit_signal("setting_changed", options.ENABLE_AUTOSHOP_OPTION_NAME, false, options.MOD_NAME)
		options.save_configs()
	if recorder != null:
		recorder.event("halt", {"reason": reason})
	set_status("HALTED: " + reason)


# A new run file was opened: export numbering and snapshot history restart.
func on_run_started():
	seq = 0
	recent_snapshots = []


# Called by ai_telemetry next to each recorder snapshot; keeps the last RECENT_MAX.
func push_snapshot(snap: Dictionary):
	recent_snapshots.append(snap.duplicate(true))
	while recent_snapshots.size() > RECENT_MAX:
		recent_snapshots.pop_front()


# Writes user://brotato-bot/state/<run_id>-<seq:03>.json (or
# norun-<YYYYMMDD-HHMMSS>-<seq:03>.json when no run is open) for player 0 and returns the path ("" when it could not be
# written). Read-only towards the game and the bot: it never shops, picks,
# steers or changes bot_state. Records an "export" event on an open recorder.
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
		recorder.event("export", {"kind": kind, "path": path, "seq": seq})
	return path


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
