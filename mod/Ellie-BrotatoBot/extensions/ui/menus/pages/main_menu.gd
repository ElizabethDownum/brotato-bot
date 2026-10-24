extends "res://ui/menus/pages/main_menu.gd"

const AutobattlerOptions = preload("res://mods-unpacked/Ellie-BrotatoBot/autobattler_options.gd")
const BotRuntime = preload("res://mods-unpacked/Ellie-BrotatoBot/bot_runtime.gd")

func _ready():
	_bot_reset()
	call_deferred("_bot_launch")
	# Create the singleton once. main_menu._ready runs on every return to the menu,
	# so without this guard each visit stacks another AutobattlerOptions node under
	# /root -- multiple _input handlers that all fire on Shift+Space, toggling the
	# flag once each (net zero) and generally corrupting the option state.
	if $"/root".has_node("AutobattlerOptions"):
		return
	var options_node = AutobattlerOptions.new()
	options_node.set_name("AutobattlerOptions")
	$"/root".add_child(options_node)


# Bot enablement never outlives a run: every visit to the main menu turns the
# bot off (Continue goes straight to the shop, skipping main.gd's guards).
# Runs before the singleton guard below so it applies on every visit.
func _bot_reset():
	var rt = BotRuntime.instance()
	if rt != null:
		rt.reset_for_menu()
		return
	# First menu visit: BotRuntime is still being added (deferred); the options
	# node, if any, is reset directly. A fresh options node starts disabled.
	var options = get_node_or_null("/root/AutobattlerOptions")
	if options != null:
		options.enable_autobattler = false
		options.enable_autoshop = false
		options.save_configs()


# Launcher: with a valid launch.json, press Start on an idle frame (see
# BotRuntime.launch_begin). BotRuntime is added deferred, so on the first menu
# visit wait for it (a few frames at most) before giving up.
func _bot_launch():
	var rt = BotRuntime.instance()
	var frames = 0
	while rt == null and frames < 120:
		yield(get_tree(), "idle_frame")
		rt = BotRuntime.instance()
		frames += 1
	if rt == null or not rt.launch_begin():
		return
	yield(get_tree(), "idle_frame")
	_on_StartButton_pressed()
