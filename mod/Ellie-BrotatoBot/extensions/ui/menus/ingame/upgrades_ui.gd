extends "res://ui/menus/ingame/upgrades_ui.gd"
# Automatic level-up choices for the AutoBattler bot. When the bot is enabled,
# whenever the level-up UI shows a player their options we pick the upgrade that
# best fits the character's build plan (ShopAdvisor.pick_upgrade), and auto-take
# any consumable/crate item. Gated by AutobattlerOptions.enable_autobattler.

const ShopAdvisor = preload("res://mods-unpacked/Ellie-BrotatoBot/shopping/shop_advisor.gd")
const BotRuntime = preload("res://mods-unpacked/Ellie-BrotatoBot/bot_runtime.gd")
const Coop = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ui/menus/run/coop_mouse_select.gd")
const RunRecorder = preload("res://mods-unpacked/Ellie-BrotatoBot/core/run_recorder.gd")
const DecisionClient = preload("res://mods-unpacked/Ellie-BrotatoBot/core/decision_client.gd")
const PickWatchdog = preload("res://mods-unpacked/Ellie-BrotatoBot/core/pick_watchdog.gd")

const PICK_WAIT = 0.3    # pace between picks -- slow enough to watch each selection land
                         # (also must exceed the container's 0.1s ButtonDelayTimer, or a
                         # rapid 2nd pick hits `if _button_pressed: return` and no-ops)

var _auto_busy = false
var _auto_heartbeat = 0        # bumped each pick; the _process watchdog watches it for stalls
var _auto_seen_heartbeat = 0
var _auto_stall_ms = 0        # processed ms since the loop's last progress (reset on a non-stall frame)
var _auto_deciding = false     # a sidecar decision is pending: the watchdog must not reclaim the loop
var _focus_outline = null


func _ready() -> void:
	._ready()
	if Coop.only_p1_is_human():
		# Start on the human's own options; TAB cycles to a still-choosing bot.
		CoopService.current_player_index = 0
		_focus_outline = Coop.make_outline()
		add_child(_focus_outline)

# Should THIS player slot's level-up be auto-picked by the bot? Mirrors the shop
# dispatch in base_shop._should_autoshop so combat, shopping and level-ups all
# agree on which slots are bot-controlled: global enable_autobattler makes every
# slot a bot (the guarded Shift+Space toggle), otherwise it is the per-slot co-op flag
# (F1-added bots). Each bot slot's per-bot autoshop toggle (CoopService.
# autoshop_by_index, default on) then gates shopping AND level-ups for that slot.
# A human slot in a mixed run returns false so the player picks it.
# The level-up / crate-pickup UI runs with CoopService.listening_for_inputs =
# false, so the FocusEmulators swallow the human's mouse clicks on the choose /
# take / discard buttons. Hold it true (when a lone human commands bots) so those
# buttons are mouse-clickable. Harmless mid-wave (those emulators focus nothing).
func _process(_delta: float) -> void:
	Coop.keep_mouse_enabled()
	# Outline the TAB-focused player's upgrade panel.
	if _focus_outline != null:
		var fpi = CoopService.current_player_index
		var fc = _get_player_container(fpi) if (fpi >= 0 and fpi < RunData.get_player_count()) else null
		Coop.update_outline_panel(_focus_outline, fc, fpi)
	# Self-healing auto-pick pump. A bot can be left with an unpicked option if the
	# loop ever exits early, or (defensively) if its coroutine dies mid-drain leaving
	# _auto_busy stuck true. Every frame: start the loop when a bot is waiting and
	# none is running; and if a loop is marked busy but has made no progress for
	# PickWatchdog.STALL_MS (1.5 s of processed time) while a bot still waits,
	# treat it as dead and reclaim it. Without this a single stall freezes the
	# whole run on the level-up screen. Time is accumulated from _delta, not the
	# wall clock: this node inherits pause, so _process stands still during a
	# human pause in Main exactly like the pause-aware pick timer does, and a
	# long pause is not mistaken for a stall on Resume. A pending decision is
	# never a stall either.
	if not _bot_is_choosing():
		_auto_stall_ms = 0
		return
	if not _auto_busy:
		_auto_pick_loop()
		return
	if _auto_deciding or get_tree().paused:
		_auto_stall_ms = 0   # waiting on the sidecar / a frozen pick timer is not a stall
		return
	if _auto_heartbeat != _auto_seen_heartbeat:
		_auto_seen_heartbeat = _auto_heartbeat
		_auto_stall_ms = 0
	else:
		_auto_stall_ms += int(_delta * 1000.0)
		if PickWatchdog.stalled(_auto_stall_ms, get_tree().paused):
			_auto_busy = false
			_auto_stall_ms = 0


func _bot_is_choosing() -> bool:
	for pi in range(RunData.get_player_count()):
		if pi < _player_is_choosing.size() and _player_is_choosing[pi] and _should_autopick(pi):
			return true
	return false

# The upgrade choose / item take-discard buttons are plain Buttons that do NOT
# receive the GUI click in co-op even with listening_for_inputs held true (the
# same blocker as the shop). So route the mouse to the option under the cursor
# directly: motion moves the selection (highlight follows the mouse), a left-click
# takes it. Only for the lone human (slot 0); bots choose via _auto_pick_loop.
var _upg_hover_ctl = null
func _input(event: InputEvent) -> void:
	if not Coop.only_p1_is_human():
		return
	# TAB cycles the active player. The level-up screen's button focus-navigation
	# consumes TAB before the CoopService global handler sees it, so cycle here too
	# (this node's _input runs before GUI focus handling).
	if event is InputEventKey and event.pressed and not event.echo and event.scancode == KEY_TAB:
		var before = CoopService.current_player_index
		Coop.cycle_focus()
		if CoopService.current_player_index != before:
			get_tree().set_input_as_handled()
		return
	# Drive the TAB-focused player's options (CoopService.current_player_index, set
	# by TAB). Only when that slot is actually choosing right now.
	var pi = CoopService.current_player_index
	if pi < 0 or pi >= _player_is_choosing.size() or not _player_is_choosing[pi]:
		return
	var container = _get_player_container(pi)
	if container == null:
		return
	var mouse = get_global_mouse_position()
	if event is InputEventMouseMotion:
		_update_upg_hover(container, mouse, pi)
		return
	if not (event is InputEventMouseButton and event.pressed and event.button_index == BUTTON_LEFT):
		return
	# Carousel arrows: switch between upgrades, inventory, and character stats.
	var car = container.carousel if ("carousel" in container) else null
	if car != null:
		if _upg_hit(car.arrow_left, mouse):
			car.index = car.index - 1
			get_tree().set_input_as_handled()
			return
		if _upg_hit(car.arrow_right, mouse):
			car.index = car.index + 1
			get_tree().set_input_as_handled()
			return
	# Reroll the upgrade options.
	if ("_reroll_button" in container) and _upg_hit(container._reroll_button, mouse):
		container._on_RerollButton_pressed()
		get_tree().set_input_as_handled()
		return
	if container._upgrades_container.visible:
		for u in [container._upgrade_ui_1, container._upgrade_ui_2, container._upgrade_ui_3, container._upgrade_ui_4]:
			if u != null and is_instance_valid(u) and u.is_visible_in_tree() \
					and u.upgrade_data != null and u.button != null \
					and u.button.get_global_rect().has_point(mouse):
				container._on_choose_button_pressed(u.upgrade_data)
				get_tree().set_input_as_handled()
				return
	elif container._items_container.visible:
		if _upg_hit(container._take_button, mouse):
			container._on_TakeButton_pressed()
			get_tree().set_input_as_handled()
		elif _upg_hit(container._discard_button, mouse):
			container._on_DiscardButton_pressed()
			get_tree().set_input_as_handled()

func _upg_hit(btn, mouse) -> bool:
	return btn != null and btn.is_visible_in_tree() and not btn.disabled and btn.get_global_rect().has_point(mouse)

# Move the keyboard selection to the choose option / item button / tab arrow under
# the cursor.
func _update_upg_hover(container, mouse, pi := 0) -> void:
	var target = null
	var car = container.carousel if ("carousel" in container) else null
	if car != null:
		if _upg_hit(car.arrow_left, mouse):
			target = car.arrow_left
		elif _upg_hit(car.arrow_right, mouse):
			target = car.arrow_right
	if target == null and ("_reroll_button" in container) and _upg_hit(container._reroll_button, mouse):
		target = container._reroll_button
	if target == null and container._upgrades_container.visible:
		for u in [container._upgrade_ui_1, container._upgrade_ui_2, container._upgrade_ui_3, container._upgrade_ui_4]:
			if u != null and is_instance_valid(u) and u.is_visible_in_tree() \
					and u.upgrade_data != null and u.button != null \
					and u.button.get_global_rect().has_point(mouse):
				target = u.button
				break
	elif target == null and container._items_container.visible:
		for btn in [container._take_button, container._discard_button, container._ban_button]:
			if _upg_hit(btn, mouse):
				target = btn
				break
	if target != null and target != _upg_hover_ctl:
		_upg_hover_ctl = target
		# The co-op upgrade container navigates with its OWN focus_emulator (set in
		# _show_next_player_options); focus through it, not the default one.
		var fe = container.focus_emulator if ("focus_emulator" in container) else null
		Utils.focus_player_control(target, pi, fe)

func _should_autopick(pi) -> bool:
	var opts = get_node_or_null("/root/AutobattlerOptions")
	if opts == null:
		return false
	# Guard (all slots, co-op bot slots included): the bot is acting on the bot
	# profile. may_act() halts the bot when it is acting on the wrong profile.
	var rt = BotRuntime.instance()
	if rt == null or not rt.may_act():
		return false
	# A co-op bot slot (F1-added) uses its OWN per-slot AUTO-SHOP toggle, checked
	# FIRST -- independent of the global AutoBattler switch, which may be on for the
	# human's own AI assist. This mirrors the combat gate (player_movement_behavior:
	# AI runs when enable_autobattler OR is_bot_by_index[pi]); checking the global
	# flag first here instead would ignore the per-bot toggles in co-op.
	var coop = get_node_or_null("/root/CoopService")
	if coop != null and pi < coop.is_bot_by_index.size() and coop.is_bot_by_index[pi]:
		return pi < coop.autoshop_by_index.size() and coop.autoshop_by_index[pi]
	# Otherwise the bot plays every slot: the global enable_autoshop flag
	# decides (default OFF; Shift+Space sets it with enable_autobattler).
	if opts.enable_autobattler:
		return opts.enable_autoshop
	return false

func _bot_may_continue() -> bool:
	var rt = BotRuntime.instance()
	return rt != null and rt.bot_may_continue()

func _any_autopick() -> bool:
	for pi in range(RunData.get_player_count()):
		if _should_autopick(pi):
			return true
	return false

# Not cached here: UpgradesUI lives for the whole run, and get_plan is cheap
# (PlanFile.load_cached re-reads plan.json only when its mtime changes), so
# every level-up sees the current plan file. Per player: co-op players can be
# different characters.
func _plan_for(player_index):
	var c = RunData.get_player_character(player_index)
	return ShopAdvisor.get_plan(c.my_id if c != null else "")

func _show_next_player_options() -> bool:
	var r = ._show_next_player_options()
	if r and _any_autopick() and not _auto_busy:
		_auto_pick_loop()
	return r

# Drains the whole level-up queue: pick for every player currently choosing,
# then let each choice surface the next option (which re-enters here, guarded by
# _auto_busy) until nobody is choosing.
# The pacing wait is pause-aware (create_timer(t, false)), and every yield is
# followed by BotRuntime.bot_may_continue: a halt or a pause by anyone but
# decide() ends this drain at once (no pick, no take/discard). The first pick
# resumes main._on_EndWaveTimer_timeout's scene change (decompiled
# main.gd:1162-1177), so it must never happen behind a pause menu.
func _auto_pick_loop() -> void:
	_auto_busy = true
	_auto_stall_ms = 0
	var guard = 0
	while guard < 60:
		guard += 1
		var acted = false
		for pi in range(RunData.get_player_count()):
			if pi >= _player_is_choosing.size() or not _player_is_choosing[pi]:
				continue
			if not _should_autopick(pi):
				continue   # human slot in a mixed run: let the player choose
			var container = _get_player_container(pi)
			yield(get_tree().create_timer(PICK_WAIT, false), "timeout")
			if not _bot_may_continue():
				_auto_busy = false
				return   # halted or paused meanwhile: act no further
			if not _should_autopick(pi) or not _player_is_choosing[pi]:
				continue   # resolved (or no longer a bot slot) while we waited
			# A bot IS still waiting on this slot, so mark progress up front: never
			# break out of the drain while any bot has an option, even if a pick is
			# momentarily blocked by the button-delay or the option list is empty.
			acted = true
			_auto_heartbeat += 1
			if container._upgrades_container.visible:
				var ups = container._old_upgrades
				if ups != null and ups.size() > 0:
					var plan = _plan_for(pi)
					var ask = _levelup_options(ups, plan, pi)
					var rt = BotRuntime.instance()
					# Ask only while a sidecar is alive; otherwise source stays "rule".
					var why = ""
					if rt.sidecar_ready():
						why = DecisionClient.should_ask(ask.scores, ask.affordable, rt.config,
							ask.ids, plan.get("ask_on", []))
					var source = "rule"
					var decision_id = ""
					var idx = -1
					if why != "":
						_auto_deciding = true
						var r = yield(rt.decide("pivot" if why == "pivot" else "levelup", ask.options, "levelup"), "completed")
						_auto_deciding = false
						_auto_heartbeat += 1
						decision_id = str(rt.last_decision.get("id", ""))
						if not _bot_may_continue():
							_auto_busy = false
							return   # halted, or a pause menu is open: no pick
						# The game was paused; re-check that this exact choice is still up.
						var still_up = _should_autopick(pi) and _player_is_choosing[pi] \
								and container._upgrades_container.visible and container._old_upgrades == ups
						if not still_up:
							continue
						if r != null and r.action == "pick" and int(r.option_index) < ask.ups_index.size():
							idx = ask.ups_index[int(r.option_index)]
							source = "haiku"
						elif r == null and rt.last_decision.get("source", "") == "timeout":
							source = "timeout"
					if idx < 0:
						idx = ShopAdvisor.pick_upgrade(ups, plan, pi)
					idx = int(clamp(idx, 0, ups.size() - 1))
					# The container's choose handler no-ops while its button delay runs
					# (decompiled upgrades_ui_player_container.gd:203-206): record
					# only a pick that actually lands.
					var landed = not container._button_pressed
					container._on_choose_button_pressed(ups[idx])
					if landed:
						_record_levelup(rt, ups[idx], ask.options, source, decision_id)
			elif container._items_container.visible:
				# A crate/consumable item is shown. Items are free stats -- take
				# them. But an off-plan WEAPON (wrong set/type, e.g. a plank for
				# elemental Mage) does ~0 damage and would waste a weapon slot, so
				# recycle it for gold instead.
				var idata = container._item_data
				var crate_plan = _plan_for(pi)
				var crate_score = ShopAdvisor.score_shop_entry([idata, 0], crate_plan, pi)
				var crate_action = "take"
				if idata is WeaponData and ShopAdvisor.score_weapon(idata, crate_plan, pi) < 0.0:
					crate_action = "recycle"
				# Both handlers no-op while the button delay runs (decompiled
				# upgrades_ui_player_container.gd:212-224); idata and the score are
				# taken above, before an accepted take advances the queue.
				var crate_landed = not container._button_pressed
				if crate_action == "recycle":
					container._on_DiscardButton_pressed()
				else:
					container._on_TakeButton_pressed()
				if crate_landed:
					_record_crate(idata, crate_action, crate_score)
				acted = true
		if not acted:
			break
	_auto_busy = false

# The level-up options for a sidecar decision. Null entries are skipped;
# option i (options[i].index == i, the response's option_index) is
# ups[ups_index[i]]:
#   options     [{index, id, stat, value, score}] (stat/value: the first effect)
#   scores      each option's ShopAdvisor.stat_score
#   affordable  every option index (level-ups cost nothing)
#   ids         each option's upgrade id (matched against the plan's ask_on)
func _levelup_options(ups, plan, pi) -> Dictionary:
	var out = {"options": [], "ups_index": [], "scores": [], "affordable": [], "ids": []}
	for j in range(ups.size()):
		var u = ups[j]
		if u == null:
			continue
		var i = out.options.size()
		var sc = float(ShopAdvisor.stat_score(u.effects, plan, pi))
		var stat = ""
		var value = 0
		if u.effects.size() > 0 and u.effects[0] != null:
			stat = str(u.effects[0].key)
			value = u.effects[0].value
		out.options.append({"index": i, "id": u.my_id, "stat": stat, "value": value, "score": sc})
		out.ups_index.append(j)
		out.scores.append(sc)
		out.affordable.append(i)
		out.ids.append(u.my_id)
	return out

# One crate event per crate item taken or recycled (telemetry only).
func _record_crate(idata, action, score) -> void:
	var rt = BotRuntime.instance()
	if rt == null or rt.recorder == null or not rt.recorder.is_open():
		return
	rt.recorder.event("crate", RunRecorder.crate_event(RunData.current_wave, idata.my_id, action, score))

# One levelup event per bot pick: {wave, id (the decision's id, "" when not
# asked), picked (upgrade id), alternatives (every option offered, with
# scores), source: "haiku" (the sidecar's pick), "rule" (not asked, or the
# answer was invalid / not a usable pick) or "timeout"}.
func _record_levelup(rt, picked, options, source, decision_id) -> void:
	if rt.recorder == null or not rt.recorder.is_open():
		return
	rt.recorder.event("levelup", {"wave": RunData.current_wave, "id": decision_id,
		"picked": picked.my_id, "alternatives": options, "source": source})
