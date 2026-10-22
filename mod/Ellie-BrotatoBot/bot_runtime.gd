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

const BotConfig = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_config.gd")
const Guards = preload("res://mods-unpacked/Ellie-BrotatoBot/core/guards.gd")

const NODE_NAME = "BotRuntime"

var recorder = null
var config = {}
var run_id = ""
var bot_state = "idle"
var last_decision = {}
var status_text = ""
var focus_warned_run_id = null

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
