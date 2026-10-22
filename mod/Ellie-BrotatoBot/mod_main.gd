extends Node

const MOD_DIR = "Ellie-BrotatoBot/"
const BotPaths = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_paths.gd")
const BotRuntime = preload("res://mods-unpacked/Ellie-BrotatoBot/bot_runtime.gd")

var dir = ""
var ext_dir = ""
var trans_dir = ""

func _init():
	dir = ModLoaderMod.get_unpacked_dir() + MOD_DIR
	ext_dir = dir + "extensions/"
	trans_dir = dir + "translations/"
	
	# Add extensions
	ModLoaderMod.install_script_extension(ext_dir + "main.gd")
	
	ModLoaderMod.install_script_extension(ext_dir + "entities/units/movement_behaviors/player_movement_behavior.gd")
	ModLoaderMod.install_script_extension(ext_dir + "entities/units/player/player.gd")
	
	ModLoaderMod.install_script_extension(ext_dir + "singletons/coop_service.gd")
	ModLoaderMod.install_script_extension(ext_dir + "singletons/input_service.gd")
	ModLoaderMod.install_script_extension(ext_dir + "singletons/cursor_manager.gd")
	ModLoaderMod.install_script_extension(ext_dir + "singletons/progress_data.gd")
	ModLoaderMod.install_script_extension(ext_dir + "singletons/run_data.gd")
	
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/global/focus_emulator.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/ingame/upgrades_ui.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/shop/base_shop.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/pages/main_menu.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/run/coop_join_panel.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/run/character_selection.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/run/difficulty_selection/difficulty_selection.gd")
	ModLoaderMod.install_script_extension(ext_dir + "ui/menus/run/weapon_selection.gd")
	
	ModLoaderMod.add_translation(trans_dir + "autobattler_options.en.translation")

	_write_probe()


func _ready():
	# One BotRuntime under /root for the whole session. Deferred: /root may still
	# be adding its autoload children while the mod loader runs.
	var root = get_tree().root
	if root.has_node(BotRuntime.NODE_NAME):
		return
	var runtime = BotRuntime.new()
	runtime.set_name(BotRuntime.NODE_NAME)
	root.call_deferred("add_child", runtime)


# Steam Cloud measurement (learnings/steam-cloud.md): a small file under
# BotPaths.ROOT whose name can be searched for in Steam's remotecache.vdf.
func _write_probe():
	var d = Directory.new()
	if d.make_dir_recursive(BotPaths.ROOT) != OK:
		push_warning("BrotatoBot: cannot create %s" % BotPaths.ROOT)
		return
	var f = File.new()
	if f.open(BotPaths.ROOT + "/probe.txt", File.WRITE) != OK:
		push_warning("BrotatoBot: cannot write probe.txt")
		return
	var dt = OS.get_datetime()
	f.store_line("%04d-%02d-%02dT%02d:%02d:%02d" % [
		dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second])
	f.close()
