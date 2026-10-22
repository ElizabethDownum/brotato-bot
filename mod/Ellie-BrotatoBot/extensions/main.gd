extends "res://main.gd"

const AICanvas  = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_canvas.gd")
const AITelemetry = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_telemetry.gd")
const CoopFocusHud = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/coop_focus_hud.gd")
const RunRecorder = preload("res://mods-unpacked/Ellie-BrotatoBot/core/run_recorder.gd")
const BotPaths = preload("res://mods-unpacked/Ellie-BrotatoBot/core/bot_paths.gd")
const PlanFile = preload("res://mods-unpacked/Ellie-BrotatoBot/core/plan_file.gd")
const Guards = preload("res://mods-unpacked/Ellie-BrotatoBot/core/guards.gd")
const Checkpoint = preload("res://mods-unpacked/Ellie-BrotatoBot/core/checkpoint.gd")
const DecisionClient = preload("res://mods-unpacked/Ellie-BrotatoBot/core/decision_client.gd")

const MOD_ID = "Ellie-BrotatoBot"

var canvas_layer
var ai_telemetry
var coop_focus_hud

# Enemies player-killed this wave (main.tscn is reloaded every wave).
var _bot_kills_this_wave = 0
# Killer id written into player 0's death event ("" until player 0 dies).
var _bot_killer = ""


# Godot 3 runs the base main.gd _ready first, so RunData is populated here.
func _ready():
	canvas_layer = AICanvas.new()
	add_child(canvas_layer)
	ai_telemetry = AITelemetry.new()
	add_child(ai_telemetry)
	coop_focus_hud = CoopFocusHud.new()
	add_child(coop_focus_hud)
	_bot_start_recording()
	_bot_run_guards()
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
	rt.on_run_started()


# Every wave start: warn once per run if the game would pause when the window
# loses focus, then halt a bot that is on while the profile is not the bot
# profile (e.g. the profile changed after enabling). Halt last so its status wins.
func _bot_run_guards():
	var rt = get_node_or_null("/root/BotRuntime")
	if rt == null:
		return
	if not Guards.focus_setting_ok(ProgressData.settings) and rt.focus_warned_run_id != rt.run_id:
		rt.focus_warned_run_id = rt.run_id
		var rec = _bot_recorder()
		if rec != null:
			rec.event("warning", {"reason": "pause_on_focus_lost is true"})
		rt.set_status("Warning: pause_on_focus_lost is true")
	# may_act() halts an acting bot that is on the wrong profile.
	var _ok = rt.may_act()


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
	if rec != null:
		var p = _bot_player0()
		rec.event("wave_end", {
			"wave": RunData.current_wave,
			"hp": int(p.current_stats.health) if p != null else 0,
			"gold": RunData.get_player_gold(0),
			"damage_taken": ai_telemetry.damage_taken_this_wave(),
			"kills": _bot_kills_this_wave,
		})
	var _cp = _bot_checkpoint()


# Target checkpoint (coroutine, started from the end_of_the_wave handler).
# end_of_the_wave is emitted from _on_WaveTimer_timeout; once this yields, the
# base game carries on into clean_up_room (which runs _set_run_states) with the
# tree paused, and the scene change waits for EndWaveTimer, which does not run
# while paused. Due once per run after the target fired, never on the final
# wave of a normal run (Checkpoint.due: the completion gate owns it). Waits
# while the bot is not acting (stays pending for a later wave end). Without a
# live sidecar it is recorded as skipped with reason "no_sidecar", no pause
# (decide()'s contract: ask only while sidecar_alive). Otherwise
# decide("checkpoint", []) pauses up to checkpoint_timeout_ms; a revise_plan
# answer is applied like the shop's (BotRuntime.apply_plan_patch), anything
# else is a skip. Records checkpoint {id, action, applied: "revise_plan" |
# "skip" | "timeout"} (plus reason when skipped without asking or when the
# patch could not be saved).
func _bot_checkpoint():
	var rt = get_node_or_null("/root/BotRuntime")
	if rt == null or rt.bot_state != "acting":
		return
	if not Checkpoint.due(rt.target_fired, rt.checkpoint_done, RunData.current_wave,
			RunData.nb_of_waves, RunData.is_endless_run):
		return
	rt.checkpoint_done = true
	if not DecisionClient.sidecar_alive(BotPaths.ROOT, OS.get_unix_time()):
		_bot_record_checkpoint(rt, {"id": "", "action": null, "applied": "skip", "reason": "no_sidecar"})
		return
	var r = yield(rt.decide("checkpoint", []), "completed")
	var applied = Checkpoint.wanted(r)
	var entry = {"id": rt.last_decision.get("id", ""),
		"action": r.get("action") if r != null else null}
	if applied == "revise_plan":
		var ch = RunData.get_player_character(0) if RunData.get_player_count() > 0 else null
		if not rt.apply_plan_patch(ch.my_id if ch != null else "", r.plan_patch):
			applied = "skip"
			entry["reason"] = "patch_not_applied"
	entry["applied"] = applied
	_bot_record_checkpoint(rt, entry)


func _bot_record_checkpoint(rt, data):
	if rt.recorder != null and rt.recorder.is_open():
		rt.recorder.event("checkpoint", data)


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
		_bot_killer = ai_telemetry.last_killer()
	._on_player_died(p_player, _args)


func _set_run_states() -> void:
	._set_run_states()
	if _is_run_won or _is_run_lost:
		call_deferred("_bot_end_run", "won" if _is_run_won else "death")


func _bot_end_run(outcome):
	var rt = get_node_or_null("/root/BotRuntime")
	# Completion gate: the single place a bot run is marked complete (player 0's
	# death and the final wave both arrive here via _set_run_states). It runs
	# whether or not the run file is open (complete() tolerates no recorder),
	# and before end_run because the recorder drops events once end_run has
	# closed the file, so the JSONL ends ...complete, end. The end line keeps
	# its won/death words; complete() takes win/death. Once complete, bot_state
	# is no longer acting, so a repeated call does not complete again.
	if rt != null and (rt.bot_state == "acting" or rt.bot_state == "deciding"):
		var extra = {}
		if outcome != "won":
			extra["killer"] = _bot_killer
		rt.complete(Guards.normalize_outcome(outcome), extra)
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
	if rt != null:
		rt.run_id = ""
