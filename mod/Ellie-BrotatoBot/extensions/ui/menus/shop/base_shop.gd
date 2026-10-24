extends "res://ui/menus/shop/base_shop.gd"
# Automatic shopping for the AutoBattler bot. When the bot is enabled, on shop
# entry it scores the offering with ShopAdvisor and buys / rerolls / leaves the
# shop on its own. Gated by AutobattlerOptions.enable_autobattler so ordinary
# human runs are completely untouched.

const ShopAdvisor = preload("res://mods-unpacked/Ellie-BrotatoBot/shopping/shop_advisor.gd")
const BotRuntime = preload("res://mods-unpacked/Ellie-BrotatoBot/bot_runtime.gd")
const Coop = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ui/menus/run/coop_mouse_select.gd")
const DecisionClient = preload("res://mods-unpacked/Ellie-BrotatoBot/core/decision_client.gd")
const TurnRulings = preload("res://mods-unpacked/Ellie-BrotatoBot/core/turn_rulings.gd")
const RunRecorder = preload("res://mods-unpacked/Ellie-BrotatoBot/core/run_recorder.gd")

const SETUP_WAIT = 0.35   # let _ready() finish populating the offering + UI
const BUY_WAIT = 0.09     # container enforces a 0.05s buy lockout; clear it
const REROLL_WAIT = 0.12
const GO_WAIT = 0.15
const MAX_ACTIONS = 250   # hard stop against any pathological loop (buys + rerolls, incl. surplus-spend)
const LOCK_MIN_SCORE = 28.0  # only save for a weapon at least this good (tier 2+ on-plan, or a combine)
const LOCK_REACH = 70        # only save if its price is within ~one wave's income of current gold
const SURPLUS_KEEP = 120     # spend_surplus: keep rerolling while gold stays above this
const SURPLUS_MAX_REROLLS = 45  # spend_surplus: hard cap on total rerolls per shop
const HUNT_KEEP = 30         # reroll-to-find (prefer_weapons): keep at least this much gold to buy the weapon once found (30 surfaced tasers + a taser_4 win; 60 was too passive to find any)
const HUNT_MAX_REROLLS = 15  # reroll-to-find: hard cap on hunt rerolls per shop

var _focus_outline = null
var _prev_ban_cur = -1   # last slot whose ban buttons were restored on TAB focus change

func _ready() -> void:
	._ready()
	Coop.keep_mouse_enabled()
	if Coop.only_p1_is_human():
		# Start each shop on the human's own panel; TAB cycles to a bot's shop.
		CoopService.current_player_index = 0
		_focus_outline = Coop.make_outline()
		add_child(_focus_outline)
	if _any_autoshop():
		call_deferred("_auto_shop")

# The co-op shop container (panel) for slot pi, or null. _get_coop_player_container
# is CoopShop-only, so invoke it dynamically to satisfy the BaseShop parser.
func _shop_panel(pi):
	if not has_method("_get_coop_player_container"):
		return null
	return call("_get_coop_player_container", pi)

# The shop enters with CoopService.listening_for_inputs = false, which makes the
# FocusEmulators swallow the human's mouse clicks. Hold it true (when a lone human
# is commanding bots) so buy / reroll / go and owned-gear clicks work by mouse.
func _process(_delta: float) -> void:
	Coop.keep_mouse_enabled()
	# Outline the TAB-focused player's shop panel. current_player_index (set by TAB,
	# CoopService._input) is the slot the human's mouse + keyboard drive; the base
	# FocusEmulators already process that slot, so no pin is needed here anymore.
	if _focus_outline != null:
		var pi = CoopService.current_player_index
		Coop.update_outline_panel(_focus_outline, _shop_panel(pi), pi)
	# Suppress the cross-player ban flicker at the source. The device-7 remap can
	# fire a non-focused player's ban button (banning their selected item; the
	# on_shop_item_banned guard then undoes it -- a visible blip). A disabled ban
	# button makes _on_BanButton_button_down early-return, so keep every non-focused
	# player's ban buttons disabled. The focused slot keeps the base's own handling
	# (so the human can still ban there); bots auto-ban via _apply_bans, which calls
	# the container directly and never touches these buttons.
	if Coop.only_p1_is_human():
		var cur = CoopService.current_player_index
		# On a TAB focus change, restore the newly-focused player's ban buttons (they
		# were held disabled while another slot was focused) via the base's own logic.
		if cur != _prev_ban_cur:
			_prev_ban_cur = cur
			var ccont = _get_shop_items_container(cur)
			if ccont != null:
				for cit in ccont._shop_items:
					if cit != null and is_instance_valid(cit) and cit.has_method("manage_ban_button_visibility"):
						cit.manage_ban_button_visibility()
		for p in range(RunData.get_player_count()):
			if p == cur:
				continue
			var cont = _get_shop_items_container(p)
			if cont == null:
				continue
			for it in cont._shop_items:
				if it != null and is_instance_valid(it) and ("_ban_button" in it) and it._ban_button != null:
					it._ban_button.disabled = true

# The shop's buy / reroll / go buttons are plain Buttons that do NOT receive the
# GUI click in co-op even with listening_for_inputs held true. Route the mouse to
# the item / button under the cursor directly (same hit-test as the level-up
# screen): motion drives hover (item popup + highlight), a left-click buys / rerolls
# / goes. Only for the lone human (slot 0); bots shop via _auto_shop_player.
var _shop_hover_item = null
func _input(event: InputEvent) -> void:
	# Solo 'e'-lock fix: do NOT forward the ui_select press to the base _input. BaseShop's
	# lock-on-select code is dead in vanilla solo (Shop._input never calls super); this
	# extension's wrapper was resurrecting it, and it double-toggled against the scene's
	# own native lock handler -- lock+unlock on every press, i.e. 'e' appeared dead while
	# mouse-clicking the lock button (single toggle) worked. Step aside WITHOUT consuming,
	# so the native handler stays the one and only lock path, exactly like an unmodded game.
	if not RunData.is_coop_run and event is InputEventKey and event.pressed and not event.echo \
			and event.is_action_pressed("ui_select"):
		return
	# TAB cycles the active player. Intercept it BEFORE the base _input (the shop's
	# carousel / focus navigation consumes TAB before the CoopService global handler).
	if Coop.only_p1_is_human() and event is InputEventKey and event.pressed \
			and not event.echo and event.scancode == KEY_TAB:
		var before = CoopService.current_player_index
		Coop.cycle_focus()
		if CoopService.current_player_index != before:
			get_tree().set_input_as_handled()
		return
	# Coop-ban scoping. The base _input loop drives the ban on EVERY player whose
	# is_player_ui_coop_ban_pressed is true, and the device-7 remap makes that true
	# for all players from one key -- so a ban press starts the ban on every focused
	# item at once (every open ban dialog fires). Handle the ban ONLY for the TAB-
	# focused player and consume it, so the base loop never bans the others.
	if Coop.only_p1_is_human():
		var bpi = CoopService.current_player_index
		if bpi >= 0 and bpi < RunData.get_player_count():
			if Utils.is_player_ui_coop_ban_pressed(event, bpi):
				_shop_ban_press(bpi)
				get_tree().set_input_as_handled()
				return
			if Utils.is_player_ui_coop_ban_released(event, bpi):
				_shop_ban_release(bpi)
				get_tree().set_input_as_handled()
				return
	._input(event)
	if not Coop.only_p1_is_human():
		# Plain solo: nothing more to do -- 'e' locking is handled by the scene's own native
		# path (this wrapper steps aside for ui_select above), and the FocusEmulator is held
		# dormant (see focus_emulator.gd), so input behaves exactly like an unmodded game.
		return
	# Act on the TAB-focused player's shop region (their items/buttons are hit-tested
	# under the cursor). Defaults to slot 0 (the human) until TAB cycles.
	var pi = CoopService.current_player_index
	if pi < 0 or pi >= RunData.get_player_count():
		pi = 0
	# When the owned-gear actions popup is OPEN (its cancel button is showing --
	# buttons_enabled is always true in the scene, so gate on real visibility),
	# its combine / discard / cancel buttons take the mouse.
	var popup = _get_item_popup(pi)
	if popup != null and popup._cancel_button != null and popup._cancel_button.is_visible_in_tree():
		_handle_shop_popup(popup, event)
		return
	if pi < _player_pressed_go_button.size() and _player_pressed_go_button[pi]:
		return   # this slot already pressed GO -- done shopping
	if event is InputEventMouseMotion:
		_update_shop_hover(pi)
		return
	# Lock ('e' / ui_select) the hovered item for the TAB-focused player. In co-op the base
	# loop's is_player_select_pressed uses the shared device-7 "ui_select_7" action, which
	# the physical 'e' never fires, so the base never locks here -- drive it ourselves.
	if event is InputEventKey and event.pressed and not event.echo and event.is_action_pressed("ui_select"):
		_shop_lock_hovered(pi)
		return
	# Space / ui_accept opens the actions popup on the hovered OWNED weapon/item --
	# the device-specific ui_accept never fires for the remapped keyboard slot, so
	# press the hovered gear element ourselves (its press emits element_pressed,
	# which the popup manager routes to the actions handler).
	if event is InputEventKey and event.pressed and not event.echo and event.is_action_pressed("ui_accept"):
		if _shop_hover_item != null and is_instance_valid(_shop_hover_item) and _shop_hover_item is InventoryElement:
			_shop_hover_item._on_InventoryElement_pressed()
			get_tree().set_input_as_handled()
		return
	if not (event is InputEventMouseButton and event.pressed and event.button_index == BUTTON_LEFT):
		return
	var mouse = get_global_mouse_position()
	# Tab arrows: switch the carousel between the shop and the character stats.
	var car = _shop_carousel(pi)
	if car != null:
		if _shop_hit(car.arrow_left, mouse):
			car.index = car.index - 1
			get_tree().set_input_as_handled()
			return
		if _shop_hit(car.arrow_right, mouse):
			car.index = car.index + 1
			get_tree().set_input_as_handled()
			return
	# Buy the shop item under the cursor.
	var over = _shop_item_at(pi, mouse)
	if over != null:
		_get_shop_items_container(pi).on_shop_item_buy_button_pressed(over)
		get_tree().set_input_as_handled()
		return
	# Reroll / Go.
	if _shop_hit(_get_reroll_button(pi), mouse):
		_on_RerollButton_pressed(pi)
		get_tree().set_input_as_handled()
		return
	if _shop_hit(_get_go_button(pi), mouse):
		_on_GoButton_pressed(pi)
		get_tree().set_input_as_handled()

# Toggle the lock on the shop item under the cursor (or the focused one).
func _shop_lock_hovered(pi) -> void:
	var target = _shop_item_at(pi, get_global_mouse_position())
	if target == null and pi < _focused_shop_item.size():
		target = _focused_shop_item[pi]
	if target == null or not is_instance_valid(target) or target.item_data == null:
		return
	if not target.item_data.is_lockable or RunData.get_player_effect_bool(Keys.disable_item_locking_hash, pi):
		return
	target.change_lock_status(not target.locked)
	get_tree().set_input_as_handled()

# Drive the ban press / release on ONLY player pi's focused shop item, mirroring
# the base _input loop's conditions -- so the human's single ban key bans just the
# TAB-focused player, never every player's focused item at once.
func _shop_ban_target(pi):
	if pi < 0 or pi >= _focused_shop_item.size():
		return null
	var item = _focused_shop_item[pi]
	if item == null or not is_instance_valid(item) or item.item_data == null or item.item_data is WeaponData:
		return null
	var pdata = RunData.players_data[pi]
	if pdata.remaining_ban_token <= 0 or pdata.banned_items.has(item.item_data.my_id_hash):
		return null
	return item

func _shop_ban_press(pi) -> void:
	if not ChallengeService.is_challenge_completed(ChallengeService.chal_banned_items_hash) \
			or not RunData.is_ban_active_in_current_run():
		return
	# Cancel any ban HOLD still filling on another player before starting this one.
	# The device-7 remap lets a single key start a hold on any focused item; if one
	# was left open on a different player it would complete on its own (a second
	# ban). Clearing ban_button_presed stops that fill loop WITHOUT banning.
	for other in range(RunData.get_player_count()):
		if other != pi and other < _focused_shop_item.size():
			var oitem = _focused_shop_item[other]
			if oitem != null and is_instance_valid(oitem) and ("ban_button_presed" in oitem) and oitem.ban_button_presed:
				oitem.ban_button_presed = false
	var item = _shop_ban_target(pi)
	if item != null:
		item._on_BanButton_button_down()

func _shop_ban_release(pi) -> void:
	var item = _shop_ban_target(pi)
	if item != null:
		item._release_BanButton()

# DIAGNOSTIC: fires for every ban regardless of path -- if one ban action logs
# multiple players, the multi-ban is happening (and via what index).
func on_shop_item_banned(shop_item, player_index) -> void:
	# Ban-scope guard (catch-all). The device-7 remap lets one ban key reach every
	# player's focused item, so a single ban can land on a slot other than the TAB-
	# focused one. Every ban -- whatever triggered it -- funnels through here, so if
	# it hit a NON-focused player (and it isn't a bot auto-banning its own shop),
	# reverse it: restore the token, drop it from the banned list, re-activate the
	# item, and DON'T remove it from the offering.
	if Coop.only_p1_is_human() and not CoopService.auto_banning \
			and player_index != CoopService.current_player_index:
		var pdata = RunData.players_data[player_index]
		pdata.banned_items.erase(shop_item.item_data.my_id_hash)
		pdata.remaining_ban_token += 1
		if shop_item.has_method("activate"):
			shop_item.activate()
		return
	.on_shop_item_banned(shop_item, player_index)

# The shop item under the cursor for slot pi, or null.
func _shop_item_at(pi, mouse):
	var container = _get_shop_items_container(pi)
	if container == null:
		return null
	for item in container._shop_items:
		if item != null and is_instance_valid(item) and item.active \
				and item.is_visible_in_tree() and item.get_global_rect().has_point(mouse):
			return item
	return null

# Move the keyboard selection to whatever the cursor is over as it moves --
# shop item, reroll/go button, or an owned weapon/item -- so the highlight and
# popup follow the mouse like an up/down nav (and lock/ban act on the hovered
# shop item). Focusing the control drives the same focus_entered chain the
# FocusEmulator uses.
func _update_shop_hover(pi) -> void:
	var target = _shop_hover_target(pi, get_global_mouse_position())
	if target == null or target == _shop_hover_item:
		return
	_shop_hover_item = target
	Utils.focus_player_control(target, pi)

# The carousel (shop <-> stats tabs) for slot pi, or null.
func _shop_carousel(pi):
	# _get_coop_player_container is CoopShop-only (not declared on BaseShop), so
	# invoke it dynamically to satisfy the parser.
	if not has_method("_get_coop_player_container"):
		return null
	var c = call("_get_coop_player_container", pi)
	return c.carousel if (c != null and ("carousel" in c)) else null

# The focusable control under the cursor for slot pi (its focus target), or null.
func _shop_hover_target(pi, mouse):
	var car = _shop_carousel(pi)
	if car != null:
		if _shop_hit(car.arrow_left, mouse):
			return car.arrow_left
		if _shop_hit(car.arrow_right, mouse):
			return car.arrow_right
	var items = _get_shop_items_container(pi)
	if items != null:
		for item in items._shop_items:
			if item != null and is_instance_valid(item) and item.active \
					and item.is_visible_in_tree() and item.get_global_rect().has_point(mouse):
				return item._button
	if _shop_hit(_get_reroll_button(pi), mouse):
		return _get_reroll_button(pi)
	if _shop_hit(_get_go_button(pi), mouse):
		return _get_go_button(pi)
	var gear = _get_gear_container(pi)
	if gear != null:
		for src in [gear.weapons_container, gear.items_container]:
			# The elements live under the InventoryContainer's inner Inventory
			# (_elements), not as its direct children.
			if src == null or not ("_elements" in src) or src._elements == null:
				continue
			for e in src._elements.get_children():
				if e is Control and e.is_visible_in_tree() and e.get_global_rect().has_point(mouse):
					return e
	return null

func _shop_hit(btn, mouse) -> bool:
	return btn != null and btn.is_visible_in_tree() and not btn.disabled and btn.get_global_rect().has_point(mouse)

# Mouse hover + click for the owned-gear actions popup (combine / discard / cancel).
func _handle_shop_popup(popup, event) -> void:
	var mouse = get_global_mouse_position()
	var buttons = [popup._combine_button, popup._discard_button, popup._cancel_button]
	if event is InputEventMouseMotion:
		for btn in buttons:
			if _shop_hit(btn, mouse):
				if btn != _shop_hover_item:
					_shop_hover_item = btn
					Utils.focus_player_control(btn, 0)
				break
		return
	if not (event is InputEventMouseButton and event.pressed and event.button_index == BUTTON_LEFT):
		return
	if _shop_hit(popup._combine_button, mouse):
		popup.emit_signal("item_combine_button_pressed", popup._item_data)
		get_tree().set_input_as_handled()
	elif _shop_hit(popup._discard_button, mouse):
		popup.emit_signal("item_discard_button_pressed", popup._item_data)
		get_tree().set_input_as_handled()
	elif _shop_hit(popup._cancel_button, mouse):
		popup.emit_signal("item_cancel_button_pressed", popup._item_data)
		get_tree().set_input_as_handled()

# Should the bot auto-shop for this player slot? Mirrors the combat AI's dispatch
# (player_movement_behavior.gd): the global enable_autobattler toggle makes EVERY
# slot a bot (the guarded Shift+Space toggle), while CoopService.is_bot_by_index[pi]
# flags an individual co-op slot added with F1. Then each bot slot's per-bot
# autoshop toggle (CoopService.autoshop_by_index[pi], default on) gates its shop +
# level-ups, so the shop layer can be turned off per bot, independently of combat.
func _should_autoshop(pi) -> bool:
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
	# human's own AI assist. Mirrors the combat gate (player_movement_behavior: AI
	# runs when enable_autobattler OR is_bot_by_index[pi]); checking the global flag
	# first here instead would ignore the per-bot toggles in co-op.
	var coop = get_node_or_null("/root/CoopService")
	if coop != null and pi < coop.is_bot_by_index.size() and coop.is_bot_by_index[pi]:
		return pi < coop.autoshop_by_index.size() and coop.autoshop_by_index[pi]
	# Otherwise the bot plays every slot: the global enable_autoshop flag
	# decides (default OFF; Shift+Space sets it with enable_autobattler).
	if opts.enable_autobattler:
		return opts.enable_autoshop
	return false

func _any_autoshop() -> bool:
	for pi in range(RunData.get_player_count()):
		if _should_autoshop(pi):
			return true
	return false

# One shop scene serves all co-op players (per-player containers). Drive each
# bot-controlled slot's shop in turn, then leave human slots to shop manually --
# the wave only starts once every player (bots via _on_GoButton_pressed below,
# humans by hand) has pressed GO.
# Every bot wait is pause-aware (create_timer(t, false): it does not tick while
# the tree is paused, and the shop root processes while paused, decompiled
# shop.tscn:50), and every yield is followed by _bot_continue: a halt, a pause
# by anyone but decide(), or Ellie's pause menu ends this visit with no further
# action and no GO; she finishes the shop by hand.
func _auto_shop() -> void:
	var rt = BotRuntime.instance()
	if rt != null:
		rt.begin_bot_screen()
	yield(get_tree().create_timer(SETUP_WAIT, false), "timeout")
	for pi in range(RunData.get_player_count()):
		if not _bot_continue(-1):
			return
		if _should_autoshop(pi):
			var st = _auto_shop_player(pi)
			if st is GDScriptFunctionState:
				yield(st, "completed")

# May the bot act for slot pi after a yield? BotRuntime.bot_may_continue (bot
# acting on the bot profile, tree not paused by anyone but decide(), no human
# pause) and, for pi >= 0, this slot is still bot-shopped.
func _bot_continue(pi) -> bool:
	var rt = BotRuntime.instance()
	if rt == null or not rt.bot_may_continue():
		return false
	return pi < 0 or _should_autoshop(pi)

# The pause menu opened (connected to PauseMenu "paused", decompiled
# base_shop.gd:134; the base saves the run state and hides Content,
# decompiled base_shop.gd:264-266). Tells BotRuntime that Ellie paused: the
# bot shops no further this visit, and decide() does not unpause under her menu.
func on_paused() -> void:
	.on_paused()
	var rt = BotRuntime.instance()
	if rt != null:
		rt.on_human_pause(_pause_menu)

# Auto-shop a single player: score the offering, buy / reroll / lock-and-save, GO.
func _auto_shop_player(pi) -> void:
	var character = RunData.get_player_character(pi)
	var plan = ShopAdvisor.get_plan(character.my_id if character != null else "")
	var gold_in = RunData.get_player_gold(pi)
	var rerolls = 0   # accepted rerolls only; rejected calls leave the same board
	var buys = 0
	var bought = []
	# Permanent per-character hold: Saver gains +1% damage per 25 materials KEPT,
	# a SOFT bonus that must not starve the build (the guide funds survival first
	# and keeps the rest). So the hold ramps in: nothing before wave 5, then a
	# modest slice of the bank rising with the waves, capped by the plan's floor.
	# Default 0 = the usual spend-everything economy.
	var gold_floor = 0
	if int(plan.get("gold_floor", 0)) > 0:
		var ramp = clamp((RunData.current_wave - 4) * 0.05, 0.0, 0.35)
		gold_floor = int(min(float(plan["gold_floor"]), ramp * gold_in))
	var save_floor = gold_floor   # gold reserved: floor + any locked weapon's price
	var saved_note = ""
	var saved_id = ""   # saved item my_id: rerolls can move a lock to another node
	var tried = {}   # ShopItem instance_id -> true, so a failed buy is not retried
	var rt = BotRuntime.instance()
	var turn_wave = RunData.current_wave   # still the crate queue's wave until GO
	# Live player-map reference: do not reset the turn store mid-visit.
	var ruled = rt.turn_rulings.for_player(turn_wave, pi)
	# A crate decline also releases locks carried from an earlier shop.
	for node in _get_shop_items_container(pi)._shop_items:
		if node == null or not node.active or not node.locked:
			continue
		if ruled.get(node.item_data.my_id, {}).get("verdict", "") != "decline":
			continue
		node.change_lock_status(false)
		if node.item_data.my_id == saved_id:
			save_floor = gold_floor
			saved_id = ""
			saved_note = ""
	# Proactive bans: spend the run's ban tokens to permanently remove items this
	# character never wants (e.g. medical guns on a glass cannon) -- they leave BOTH
	# this shop and all future ones (added to banned_items). Done once up front so the
	# buy loop and every later reroll are already clean.
	_apply_bans(pi, plan)
	var offer_view = 0   # the last board an offer event was recorded for (1 + rerolls)
	var asks = 0   # sidecar decisions asked this visit (should_ask caps them at ask_per_visit)
	var asked_view = 0   # the last board (offer_view) a decision was asked on: one ask per board
	var actions = 0
	var abandoned = false
	while actions < MAX_ACTIONS:
		# Re-checked after every yield (each one ends in `continue`): a halt or a
		# pause ends the visit here, before any further action.
		if not _bot_continue(pi):
			abandoned = true
			break
		actions += 1
		var gold = RunData.get_player_gold(pi)
		var container = _get_shop_items_container(pi)
		var nodes = container._shop_items
		if rerolls + 1 != offer_view:
			offer_view = rerolls + 1
			_record_offer(offer_view, gold, nodes, plan, pi)
		# Sidecar decision at most once per board of the visit (the first view and
		# each post-reroll board: a lock or a buy leaves the same board, so a locked
		# goal item does not ask twice), up to ask_per_visit times across the visit,
		# and only while a sidecar is alive (fresh
		# sidecar.alive; otherwise no request, no pause, no decision events -- the
		# rules decide): when DecisionClient.should_ask finds an ask_on id, a genuine
		# tie or a big purchase, BotRuntime.decide pauses the game and waits for
		# responses/<id>.json. The applied result
		# is recorded as a decision_applied event; "rule" means BOTato's own
		# choice below runs this iteration (timeout, invalid response, or an
		# answer that cannot be carried out).
		# "pass" declines one item id for the rest of this turn and lets the
		# rules keep shopping; "skip" ends the whole visit.
		if asked_view != offer_view and asks < int(rt.config.get("ask_per_visit", DecisionClient.DEFAULT_PER_VISIT)) and rt.sidecar_ready():
			var ask = _decision_options(nodes, gold, plan, pi, ruled)
			var why = DecisionClient.should_ask(ask.scores, ask.affordable, rt.config,
				ask.ids, plan.get("ask_on", []), plan["min_buy"], gold, ask.prices, asks, ruled)
			if why != "":
				var review_ids = plan.get("ask_on", []).duplicate()
				asks += 1
				asked_view = offer_view
				var r = yield(rt.decide("pivot" if why == "pivot" else "shop", ask.options, "shop"), "completed")
				if not _bot_continue(pi):
					abandoned = true
					break   # halted or Ellie paused while deciding: act no further, no GO
				gold = RunData.get_player_gold(pi)
				var act = str(r.action) if r != null else ""
				var oi = int(r.get("option_index", -1)) if r != null else -1
				var target = ask.nodes[oi] if oi >= 0 and oi < ask.nodes.size() else null
				if target != null and (not is_instance_valid(target) or not target.active):
					target = null
				var target_score = ask.scores[oi] if target != null else null
				var applied = "rule"
				var rulings_missing = 0
				if act == "buy" and target != null and int(target.value) <= gold:
					tried[target.get_instance_id()] = true
					if target.locked:
						target.change_lock_status(false)
						save_floor = gold_floor
						saved_id = ""
					var t_id = target.item_data.my_id
					var t_price = int(target.value)
					container.on_shop_item_buy_button_pressed(target)
					# Rejected buys leave the node active (delay / weapon restrictions).
					if not target.active:
						bought.push_back("%s@%d(ai)" % [t_id, t_price])
						buys += 1
						_record_shop(pi, "buy", t_id, t_price, target_score, "haiku")
						applied = "buy"
				elif act == "pass" and target != null:
					applied = "pass"
				elif act == "lock" and target != null:
					if not target.locked:
						target.change_lock_status(true)
					if target.locked:   # change_lock_status can no-op when locking is disabled
						tried[target.get_instance_id()] = true   # keep it, do not buy it this pass
						save_floor = gold_floor + int(target.value)
						saved_id = target.item_data.my_id
						saved_note = " lock=%s@%d(ai)" % [target.item_data.my_id, int(target.value)]
						_record_shop(pi, "lock", target.item_data.my_id, int(target.value), target_score, "haiku")
						applied = "lock"
				elif act == "reroll" and _reroll_price.size() > pi:
					var rprice = _reroll_price[pi]
					if rprice <= 0 or _free_rerolls[pi] > 0 or _has_bonus_free_reroll[pi] or gold >= rprice:
						var paid = 0 if (rprice <= 0 or _free_rerolls[pi] > 0 or _has_bonus_free_reroll[pi]) else rprice
						var ai_reroll_count_before = _reroll_count[pi]
						_on_RerollButton_pressed(pi)
						if _reroll_count[pi] > ai_reroll_count_before:
							rerolls += 1
							tried.clear()
							_record_shop(pi, "reroll", null, paid, null, "haiku")
							applied = "reroll"
				elif act == "skip":
					applied = "skip"
				elif act == "revise_plan":
					var cid = character.my_id if character != null else ""
					if rt.apply_plan_patch(cid, r.plan_patch):
						plan = ShopAdvisor.get_plan(cid)
						# A newly reviewed saving target now needs sign-off. Do not
						# carry its old reserve into the rules' reroll-keep calculation.
						# Existing Haiku locks on review ids retain their behavior.
						if saved_id != "" and not review_ids.has(saved_id) \
								and not TurnRulings.rule_allowed(saved_id, plan.get("ask_on", []), ruled):
							for node in container._shop_items:
								if node != null and node.active and node.item_data.my_id == saved_id and node.locked:
									node.change_lock_status(false)
							save_floor = gold_floor
							saved_id = ""
							saved_note = ""
						applied = "revise_plan"
				if r != null and act in ["buy", "lock", "pass", "reroll", "skip", "revise_plan"]:
					var ruling_result = rt.turn_rulings.shop_rulings(turn_wave, pi, ask.ids,
						review_ids, r, str(rt.last_decision.get("id", "")), applied)
					rulings_missing = ruling_result.missing
					for di in ruling_result.declined:
						var declined_id = ask.ids[di]
						# A reroll may reuse nodes: match the original id, not the old node.
						for node in container._shop_items:
							if node != null and node.active and node.item_data.my_id == declined_id and node.locked:
								node.change_lock_status(false)
						if declined_id == saved_id:
							save_floor = gold_floor
							saved_id = ""
							saved_note = ""
						_record_shop(pi, "pass", declined_id, ask.options[di].price, ask.scores[di], "haiku")
				_record_applied(rt, r, applied, rulings_missing)
				if applied == "skip":
					break
				if applied == "buy":
					yield(get_tree().create_timer(BUY_WAIT, false), "timeout")
					continue
				if applied == "reroll":
					yield(get_tree().create_timer(REROLL_WAIT, false), "timeout")
					continue
				if applied != "rule":
					continue   # pass / lock / revise_plan: re-loop with the new state
		# Pick the best affordable, buyable, not-yet-tried node -- but never dip
		# below save_floor (the gold held for a weapon we locked to buy later).
		# Locked nodes ARE considered here: a weapon we locked (this wave or a past
		# one) should be bought once affordable. A locked buy is exempt from
		# save_floor -- it IS the thing we were saving for.
		var best_node = null
		var best_score = plan["min_buy"]
		var best_raw_score = 0.0   # best_node's score without the locked bonus (shop event)
		for node in nodes:
			if node == null or not node.active:
				continue
			if not TurnRulings.rule_allowed(node.item_data.my_id, plan.get("ask_on", []), ruled):
				continue
			if tried.has(node.get_instance_id()):
				continue
			if node.value > gold:
				continue
			if not node.locked and gold - int(node.value) < save_floor:
				continue
			var sc = ShopAdvisor.score_shop_entry([node.item_data, node.wave_value], plan, pi)
			var raw_sc = sc
			if node.locked:
				sc += 1000.0   # buy what we committed to first
			if sc > best_score:
				best_score = sc
				best_raw_score = raw_sc
				best_node = node
		if best_node != null:
			if ruled.get(best_node.item_data.my_id, {}).get("verdict", "") == "approve":
				print("BOTLOG SHOP reuse player=%d item=%s action=buy" % [pi, best_node.item_data.my_id])
			tried[best_node.get_instance_id()] = true
			if best_node.locked:
				best_node.change_lock_status(false)   # clear the lock registration before buying
				save_floor = gold_floor                # target acquired -> back to the plan's floor
				saved_id = ""
			bought.push_back("%s@%d(%.0f)" % [best_node.item_data.my_id, int(best_node.value), best_score])
			buys += 1
			var b_id = best_node.item_data.my_id
			var b_price = int(best_node.value)
			container.on_shop_item_buy_button_pressed(best_node)
			_record_shop(pi, "buy", b_id, b_price, best_raw_score, "rule")
			yield(get_tree().create_timer(BUY_WAIT, false), "timeout")
			continue
		# Nothing affordable to buy. If a strong weapon is on offer that we cannot
		# afford yet, LOCK it and save for it (locked items survive rerolls and
		# carry to the next wave's shop), then stop -- do not reroll it away or
		# spend the saved gold.
		if save_floor == gold_floor:
			var target = _weapon_to_save_for(nodes, gold, plan, pi, ruled)
			if target != null:
				if not target.locked:
					target.change_lock_status(true)
					_record_shop(pi, "lock", target.item_data.my_id, int(target.value),
						ShopAdvisor.score_weapon(target.item_data, plan, pi), "rule")
				save_floor = gold_floor + int(target.value)
				saved_id = target.item_data.my_id
				saved_note = " lock=%s@%d" % [target.item_data.my_id, int(target.value)]
				continue   # re-loop: keep shopping with the rest of the gold
		# Keep shopping even while saving: reroll if free, or affordable while
		# still preserving save_floor (the gold held for the locked weapon).
		var price = _reroll_price[pi]
		var free = price <= 0 or _free_rerolls[pi] > 0 or _has_bonus_free_reroll[pi]
		var keep = plan["reroll_keep"]
		if save_floor > keep:
			keep = save_floor
		var can_pay = gold - price >= keep and rerolls < plan["max_rerolls"]
		# Weaponless / single-weapon characters (Bull, Beast Master, One-Armed) can
		# never spend gold on weapons, so once the shop's items thin out they bank a
		# huge surplus (300-450g = wasted damage/survival). With spend_surplus set,
		# keep rerolling past max_rerolls while a big surplus remains, to surface more
		# items/pets to buy. Bounded by SURPLUS_KEEP and a hard reroll cap.
		var surplus_spend = plan.get("spend_surplus", false) \
			and gold - price >= SURPLUS_KEEP and rerolls < SURPLUS_MAX_REROLLS
		# Reroll-to-find: a character whose survival hinges on a specific weapon
		# (Pacifist's taser STUN -- its only crowd control at -100% damage) can't
		# rely on whatever the RNG offers. While no preferred weapon is on the board
		# and a weapon slot is still open, keep rerolling (down to HUNT_KEEP) to
		# surface one. No-op for every plan without prefer_weapons.
		var hunting = not plan.get("prefer_weapons", []).empty() \
			and RunData.get_player_weapons(pi).size() < int(plan.get("max_weapons", 6)) \
			and not _offering_has_preferred(nodes, plan, ruled) \
			and gold - price >= HUNT_KEEP and rerolls < HUNT_MAX_REROLLS
		if _reroll_price.size() > pi and (free or can_pay or surplus_spend or hunting):
			var reroll_count_before = _reroll_count[pi]
			_on_RerollButton_pressed(pi)
			if _reroll_count[pi] <= reroll_count_before:
				break   # rejected: no new board to shop
			rerolls += 1
			tried.clear()   # an accepted reroll replaces the offering
			_record_shop(pi, "reroll", null, 0 if free else price, null, "rule")
			yield(get_tree().create_timer(REROLL_WAIT, false), "timeout")
			continue
		break
	print("BOTLOG SHOP player=%d wave=%d gold_in=%d gold_out=%d buys=%d rerolls=%d bought=%s%s%s" % [
		pi, RunData.current_wave, gold_in, RunData.get_player_gold(pi), buys, rerolls, str(bought), saved_note,
		" abandoned" if abandoned else ""])
	if abandoned:
		return
	yield(get_tree().create_timer(GO_WAIT, false), "timeout")
	# _on_GoButton_pressed returns at once while the tree is paused (decompiled
	# base_shop.gd:301), so a pause here would drop GO silently: check first.
	if _bot_continue(pi):
		_on_GoButton_pressed(pi)
		_record_shop(pi, "go", null, null, null, "rule")

# The scored offering for a sidecar decision. Only active, non-declined ids are options;
# approved ids remain visible with their scores. shop_options filters declines once.
# option i (options[i].index == i, the response's option_index) is nodes[i]:
#   options     [{index, id, kind: "weapon"|"item", price, score}]
#   nodes       the ShopItem node behind each option
#   scores      each option's ShopAdvisor.score_shop_entry
#   prices      each option's price
#   affordable  indices of the options whose price is <= gold
#   ids         every active, non-declined item id (matched against ask_on)
func _decision_options(nodes, gold, plan, pi, ruled) -> Dictionary:
	var entries = []
	for node in nodes:
		if node == null or not is_instance_valid(node) or not node.active:
			continue
		var sc = float(ShopAdvisor.score_shop_entry([node.item_data, node.wave_value], plan, pi))
		entries.append({
			"node": node,
			"id": node.item_data.my_id,
			"kind": "weapon" if node.item_data is WeaponData else "item",
			"price": int(node.value),
			"score": sc,
		})
	return DecisionClient.shop_options(entries, gold, ruled)

# One shop event per bot action (RunRecorder.shop_event): action "buy" |
# "reroll" | "lock" | "ban" | "go", source "rule" | "haiku", gold_after read
# right after the action (the base buy / reroll handlers update gold
# synchronously -- unverified in game). The BOTLOG SHOP summary line stays.
func _record_shop(pi, action, item_id, price, score, source) -> void:
	var rt = BotRuntime.instance()
	if rt == null or rt.recorder == null or not rt.recorder.is_open():
		return
	rt.recorder.event("shop", RunRecorder.shop_event(RunData.current_wave, action, item_id,
		price, score, source, RunData.get_player_gold(pi)))

# One offer event per board the bot sees: the first view and the board after each
# reroll (RunRecorder.offer_event). Score is the raw shop score (no locked bonus).
func _record_offer(view, gold, nodes, plan, pi) -> void:
	var rt = BotRuntime.instance()
	if rt == null or rt.recorder == null or not rt.recorder.is_open():
		return
	var items = []
	for node in nodes:
		if node == null or not is_instance_valid(node) or not node.active:
			continue
		items.append(RunRecorder.offer_item(node.item_data.my_id, node.item_data.tier, node.value,
			ShopAdvisor.score_shop_entry([node.item_data, node.wave_value], plan, pi), node.locked))
	rt.recorder.event("offer", RunRecorder.offer_event(RunData.current_wave, view, gold, items))

# Follow-up to BotRuntime's decision event: what the shop actually did.
# {id, action (the response's, or null), option_index (or null), applied:
# "buy"|"pass"|"lock"|"reroll"|"skip"|"revise_plan"|"rule"}.
func _record_applied(rt, r, applied, rulings_missing) -> void:
	if rt.recorder == null or not rt.recorder.is_open():
		return
	rt.recorder.event("decision_applied", {
		"id": rt.last_decision.get("id", ""),
		"action": r.action if r != null else null,
		"option_index": r.get("option_index") if r != null else null,
		"applied": applied,
		"rulings_missing": rulings_missing,
	})

# The weapon on offer worth saving for: a strong weapon (tier 2+ / combine) we
# cannot afford this wave but could next wave. Already-locked weapons always
# qualify (we committed to them last wave and must keep reserving), and are
# exempt from the reach cap. Returns the ShopItem node, or null.
# Is any offered weapon one of the plan's prefer_weapons (matched by my_id
# substring)? Used by reroll-to-find to stop rerolling once a taser is on the
# board (the buy loop / lock-and-save then handles acquiring it).
func _offering_has_preferred(nodes, plan, ruled) -> bool:
	var prefs = plan.get("prefer_weapons", [])
	if prefs.empty():
		return false
	for node in nodes:
		if node == null or not node.active or not (node.item_data is WeaponData):
			continue
		if not TurnRulings.rule_allowed(node.item_data.my_id, plan.get("ask_on", []), ruled):
			continue
		for pref in prefs:
			if pref in node.item_data.my_id:
				return true
	return false

func _weapon_to_save_for(nodes, gold, plan, pi, ruled):
	var best = null
	var best_sc = LOCK_MIN_SCORE
	for node in nodes:
		if node == null or not node.active:
			continue
		if not TurnRulings.rule_allowed(node.item_data.my_id, plan.get("ask_on", []), ruled):
			continue
		if not (node.item_data is WeaponData):
			continue
		if node.value <= gold:
			continue   # affordable now -> the buy loop handles it
		if not node.locked and node.value > gold + LOCK_REACH:
			continue   # a NEW lock must be reachable next wave; a kept one is not dropped
		if not node.locked and not _on_plan_weapon(node.item_data, plan, pi):
			continue   # only save for on-plan weapons -- never hold gold for an off-plan combine
		var sc = ShopAdvisor.score_weapon(node.item_data, plan, pi)
		if node.locked:
			sc += 1000.0
		if sc > best_sc:
			best_sc = sc
			best = node
	return best

# Proactive item bans. If the run has ban mode active (settings ban_mode_toggled ->
# players_data.uses_ban) and tokens remain, ban every offered shop item whose my_id is
# in the plan's ban_items list. ban_item() adds it to banned_items, so ItemService also
# filters it out of every future shop and reroll this run -- a hard, permanent version
# of avoid_weapons that never fires unless the player opted into ban mode. Fixes e.g.
# the medical-gun overrank diluting glass-cannon boards, without a scoring hack.
func _apply_bans(pi, plan) -> void:
	var bans = plan.get("ban_items", [])
	if bans.empty() or not RunData.is_ban_active_in_current_run():
		return
	var container = _get_shop_items_container(pi)
	var pdata = RunData.players_data[pi]
	# The ban-scope guard (shop_items_container) blocks bans on any non-focused
	# player's shop; this bot is legitimately banning its OWN shop, so flag it.
	CoopService.auto_banning = true
	for node in Array(container._shop_items):   # copy: banning mutates the offering
		if node == null or not node.active:
			continue
		if pdata.remaining_ban_token <= 0:
			break
		if bans.has(node.item_data.my_id) and not pdata.banned_items.has(node.item_data.my_id_hash):
			var ban_id = node.item_data.my_id
			var ban_price = int(node.value)
			container.on_shop_item_ban_button_pressed(node)
			_record_shop(pi, "ban", ban_id, ban_price, null, "rule")
			print("BOTLOG BAN player=%d wave=%d item=%s tokens_left=%d" % [
				pi, RunData.current_wave, node.item_data.my_id, pdata.remaining_ban_token])
	CoopService.auto_banning = false

# Does the weapon match this plan's weapon class (set, or melee/ranged type)?
func _on_plan_weapon(wdata, plan, pi):
	var want_set = plan.get("weapon_set", "")
	if want_set != "":
		return ShopAdvisor.weapon_in_set(wdata, want_set)
	var wt = plan.get("weapon_type", "any")
	return wt == "any" or ShopAdvisor.weapon_type_str(wdata) == wt
