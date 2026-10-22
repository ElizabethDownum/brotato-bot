extends "res://main.gd"

const AICanvas  = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_canvas.gd")
const AITelemetry = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_telemetry.gd")
const CoopFocusHud = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/coop_focus_hud.gd")
const RunRecorder = preload("res://mods-unpacked/Ellie-BrotatoBot/core/run_recorder.gd")
const BotPaths = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_paths.gd")
const PlanFile = preload("res://mods-unpacked/Ellie-BrotatoBot/core/plan_file.gd")

const MOD_ID = "Ellie-BrotatoBot"

var canvas_layer
var ai_telemetry
var coop_focus_hud

# Enemies player-killed this wave (main.tscn is reloaded every wave).
var _bot_kills_this_wave = 0


# Godot 3 runs the base main.gd _ready first, so RunData is populated here.
func _ready():
	canvas_layer = AICanvas.new()
	add_child(canvas_layer)
	ai_telemetry = AITelemetry.new()
	add_child(ai_telemetry)
	coop_focus_hud = CoopFocusHud.new()
	add_child(coop_focus_hud)
	_bot_start_recording()
	var _e = connect("end_of_the_wave", self, "_bot_on_end_of_the_wave")

func free():
	remove_child(canvas_layer)
	.free()


# Opens the run file on the first wave of a run. main.tscn reloads every wave,
# so a later wave continues the open run; a later wave with no open run (a
# resumed save, or a retried wave after the run ended) starts a new file whose
# header carries start_wave.
func _bot_start_recording():
	var rt = get_node_or_null("/root/BotRuntime")
	if rt == null:
		push_warning("BrotatoBot: /root/BotRuntime missing; run not recorded")
		return
	if RunData.get_player_count() < 1 or RunData.get_player_character(0) == null:
		return
	var open = rt.recorder != null and rt.recorder.is_open()
	if open and RunData.current_wave > 1:
		return
	if open:
		# Wave 1 again with a run still open: the last run was left via the menu.
		rt.recorder.end_run({"outcome": "abandoned", "wave": null, "hp": null, "gold": null})
	var character_id = RunData.get_player_character(0).my_id
	var plan_id = "builtin"
	var loaded = PlanFile.load_cached(PlanFile.DEFAULT_PATH)
	if typeof(loaded) == TYPE_DICTIONARY and loaded.character_id == str(character_id):
		plan_id = loaded.plan_id
	var mod_version = ""
	var mod_data = ModLoaderMod.get_mod_data(MOD_ID)
	if mod_data != null and mod_data.manifest != null:
		mod_version = mod_data.manifest.version_number
	if rt.recorder == null:
		rt.recorder = RunRecorder.new(BotPaths.ROOT)
	rt.run_id = rt.recorder.start_run({
		"character_id": character_id,
		"danger": RunData.current_difficulty,
		"plan_id": plan_id,
		"profile_id": ProgressData.current_profile_id,
		"game_version": ProgressData.VERSION,
		"mod_version": mod_version,
		"start_wave": RunData.current_wave,
	})


func _bot_recorder():
	var rt = get_node_or_null("/root/BotRuntime")
	if rt == null or rt.recorder == null or not rt.recorder.is_open():
		return null
	return rt.recorder


func _bot_player0():
	if _players.empty() or not is_instance_valid(_players[0]):
		return null
	return _players[0]


func _bot_on_end_of_the_wave():
	var rec = _bot_recorder()
	if rec == null:
		return
	var p = _bot_player0()
	rec.event("wave_end", {
		"wave": RunData.current_wave,
		"hp": int(p.current_stats.health) if p != null else 0,
		"gold": RunData.get_player_gold(0),
		"damage_taken": ai_telemetry.damage_taken_this_wave(),
		"kills": _bot_kills_this_wave,
	})


func _on_enemy_died(enemy: Enemy, args: Entity.DieArgs) -> void:
	if not _cleaning_up and args.enemy_killed_by_player:
		_bot_kills_this_wave += 1
	._on_enemy_died(enemy, args)


# Records the death before the base handler cleans up the room. The killing
# blow's damage event fires after this (player.gd calls die() before emitting
# took_damage), so the run's end line is deferred past it (_set_run_states).
func _on_player_died(p_player: Player, _args: Entity.DieArgs) -> void:
	if p_player.player_index == 0:
		var killer = ""
		var from = _args.from
		if from != null and is_instance_valid(from):
			if from is BulletHell:
				killer = "bullet_hell"
			elif "enemy_id" in from:
				killer = from.enemy_id
		ai_telemetry.record_death(p_player, killer)
	._on_player_died(p_player, _args)


func _set_run_states() -> void:
	._set_run_states()
	if _is_run_won or _is_run_lost:
		call_deferred("_bot_end_run", "won" if _is_run_won else "death")


func _bot_end_run(outcome):
	var rec = _bot_recorder()
	if rec == null:
		return
	var p = _bot_player0()
	rec.end_run({
		"outcome": outcome,
		"wave": RunData.current_wave,
		"hp": int(p.current_stats.health) if p != null else 0,
		"gold": RunData.get_player_gold(0),
	})
	var rt = get_node_or_null("/root/BotRuntime")
	if rt != null:
		rt.run_id = ""
