extends Node

# Bot telemetry for the current run, written as structured events to the run
# recorder held by /root/BotRuntime (see core/run_recorder.gd). Replaces
# BOTato's stdout BOTLOG lines and runs in release builds too.
#
#   snapshot     1 Hz while a wave runs and the bot is enabled (was BOTLOG t= / ARB)
#   damage       every unblocked hit on player 0 (was HIT, with PHIT / PCHOICE /
#                PHIST folded in as the hit / choice / hist keys)
#   death        from main.gd's _on_player_died via record_death() (was DEATH)
#   build        from main.gd's run end via record_build(), win or death
#   dash         boss dash state transitions, every frame (was DASH)
#   bullet_hell  the wave's bullet-hell variant, once per wave (was BULLETHELL)
#
# main.gd writes wave_end itself and reads damage_taken_this_wave() for it.
# Keys beyond the harness's named ones are kept on purpose: they are the tuning
# fields the BOTLOG lines carried.

const RunRecorder = preload("res://mods-unpacked/Ellie-BrotatoBot/core/run_recorder.gd")
const LootTracker = preload("res://mods-unpacked/Ellie-BrotatoBot/core/loot_tracker.gd")
const WorldView = preload("res://mods-unpacked/Ellie-BrotatoBot/steering/world_view.gd")

const INTERVAL = 1.0

var _accum = INTERVAL
var _hooked_player = null
var _damage_taken_this_wave = 0.0
var _last_wave = - 1
var _last_threats = []
var _last_damage_src = ""
var _last_killer = ""
var _boss_state_cache = {}
var _loot = LootTracker.new()
# main.tscn and this child are recreated at each wave start. Keep a monotonic
# origin: the final boss kill resets _wave_timer to 0.1 s (main.gd:520-521).
var _wave_start_msec = OS.get_ticks_msec()


func _loot_time() -> float:
	return float(OS.get_ticks_msec() - _wave_start_msec) / 1000.0


func record_loot_spawn(enemy):
	var player = get_parent()._bot_player0()
	if _recorder() == null or player == null or not enemy.is_loot:
		return
	_loot.spawn(enemy.get_instance_id(), RunData.current_wave, _loot_time(),
		player.position.distance_to(enemy.position))


func record_loot_end(enemy, args):
	var rec = _recorder()
	if rec == null or not enemy.is_loot:
		return
	var player = get_parent()._bot_player0()
	if player != null:
		_loot.observe(enemy.get_instance_id(), player.position.distance_to(enemy.position))
	var result = LootTracker.outcome(args.cleaning_up or get_parent()._cleaning_up,
		args.enemy_killed_by_player, enemy.can_drop_loot)
	var event = _loot.finish(enemy.get_instance_id(), _loot_time(), result)
	if event != null:
		rec.event("loot_alien", event)


func finish_loot_wave():
	var rec = _recorder()
	if rec == null:
		return
	# Include the final player position before base cleanup removes enemies.
	_track_loot()
	for event in _loot.finish_wave(_loot_time()):
		rec.event("loot_alien", event)


func _physics_process(_delta):
	_track_loot()


func seed_loot():
	_track_loot()


func _track_loot():
	var rec = _recorder()
	var main = get_parent()
	var player = main._bot_player0()
	if rec == null or player == null or main._cleaning_up:
		return
	var ids = []
	for enemy in main._entity_spawner.enemies:
		if not is_instance_valid(enemy) or not enemy.is_loot or enemy.dead:
			continue
		ids.append(enemy.get_instance_id())
		# Also seeds already-live aliens if main's base _ready spawned them
		# before this telemetry child existed. Normal spawn times use the hook.
		record_loot_spawn(enemy)
	for event in _loot.missing(ids, _loot_time()):
		rec.event("loot_alien", event)


func loot_snapshot(origin: Vector2) -> Dictionary:
	var positions = []
	for enemy in get_parent()._entity_spawner.enemies:
		if is_instance_valid(enemy) and enemy.is_loot and not enemy.dead and not enemy._pending_die:
			positions.append(enemy.position)
	return LootTracker.snapshot(positions, origin, WorldView.PICKUP_RANGE)


func _recorder():
	var rt = get_node_or_null("/root/BotRuntime")
	if rt == null or rt.recorder == null or not rt.recorder.is_open():
		return null
	return rt.recorder


func _process(delta):
	# Boss dash cycles (croc: ~1 s windup+dash+cooldown) fit entirely between
	# 1 Hz ticks — record state transitions every frame instead
	_track_boss_dashes()
	_accum += delta
	if _accum < INTERVAL:
		return
	_accum = 0.0
	_tick()


func _track_boss_dashes():
	if not _bot_active():
		return
	var rec = _recorder()
	if rec == null:
		return
	var main = get_parent()
	if main._players.empty():
		return
	var player = main._players[0]
	if not is_instance_valid(player) or player.dead:
		return
	for boss in main._entity_spawner.bosses:
		if not is_instance_valid(boss) or boss.dead or boss._pending_die:
			continue
		var state = "idle"
		if boss._move_locked:
			state = "dashing"
		elif not boss._can_move:
			state = "windup"
		var key = boss.get_instance_id()
		if _boss_state_cache.get(key, "") != state:
			_boss_state_cache[key] = state
			rec.event("dash", {
				"wave": RunData.current_wave, "boss": boss.enemy_id, "state": state,
				"dist": int(boss.position.distance_to(player.position)),
				"pos": _pos(player.position)})


# Largest weave amplitude among a bullet hell's generators. That is the number
# that drives threat geometry: 50 is a wobble, 600 is a bullet that crosses the
# arena sideways while travelling.
func _bh_amplitude(bh) -> float:
	var best = 0.0
	for gen in bh.get_children():
		if not ("sinusoidal_motion" in gen):
			continue
		var a = gen.sinusoidal_motion.length()
		if a > best:
			best = a
	return best


func _bot_active() -> bool:
	var options = get_node_or_null("/root/AutobattlerOptions")
	if options == null:
		return false
	return options.enable_autobattler


func _tick():
	var main = get_parent()
	if not _bot_active():
		return
	var rec = _recorder()
	if rec == null:
		return
	if main._players.empty():
		return
	var player = main._players[0]
	if not is_instance_valid(player):
		return

	_hook_player(player)

	if RunData.current_wave != _last_wave:
		_last_wave = RunData.current_wave
		_damage_taken_this_wave = 0.0
		_boss_state_cache.clear()
		# Which bullet-hell variant this wave rolled. main.gd picks it with
		# pick_random(), so it is not in the snapshot -- but the variants differ
		# 12x in weave amplitude (50 to +-600), which changes the threat geometry
		# enormously. Without this event a sweep cannot say whether it actually
		# covered the violent variants or only the mild ones.
		var projectiles = main.get_node_or_null("EnemyProjectiles")
		if projectiles:
			for child in projectiles.get_children():
				if child is BulletHell:
					rec.event("bullet_hell", {
						"wave": RunData.current_wave, "variant": child.name,
						"amp": int(_bh_amplitude(child)), "speed": child.projectile_speed})
					break

	# Deaths are recorded synchronously from main.gd (record_death).
	if player.dead:
		return

	if main._cleaning_up or main._wave_timer.time_left <= 0.05:
		return

	var spawner = main._entity_spawner
	var far = ZoneService.current_zone_max_position
	var edge = min(min(player.position.x, far.x - player.position.x),
			min(player.position.y, far.y - player.position.y))

	var near_enemy = _nearest_distance(spawner.enemies, player.position)
	var charging = _count_charging(spawner.enemies, player.position) \
			+ _count_charging(spawner.bosses, player.position)

	var proj_count = 0
	var projectiles = main.get_node_or_null("EnemyProjectiles")
	if projectiles:
		for p in projectiles.get_children():
			if p is Projectile and p._hitbox and p._hitbox.active:
				proj_count += 1

	var bosses = []
	for boss in spawner.bosses:
		if boss.dead or boss._pending_die:
			continue
		var state = "idle"
		if boss._move_locked:
			state = "dashing"
		elif not boss._can_move:
			state = "windup"
		bosses.push_back({
			"id": boss.enemy_id, "dist": int(boss.position.distance_to(player.position)),
			"hp": int(boss.current_stats.health), "st": boss._current_state, "state": state})

	# esc bitmask: +1 gap escape, +2 wave counter-steer, +4 crossfire exit,
	# +8 AoE-cluster flee, +16 single-corridor charge dodge, +32 bullet dodge,
	# +64 pillar-field navigation
	var move_behavior = player._movement_behavior
	var esc = _esc_bits(move_behavior)
	# corr = corridors actually threatening us last frame (charging counts
	# map-wide chargers and routinely overstates)
	var corr = 0
	if move_behavior and "last_corridor_count" in move_behavior:
		corr = move_behavior.last_corridor_count

	var threats = _nearby_threats(main, player, 3)
	_last_threats = threats

	var heading = Vector2.ZERO
	if move_behavior and ("last_move_dir" in move_behavior):
		heading = move_behavior.last_move_dir

	var nearest = {"id": "", "dist": - 1}
	if not threats.empty():
		nearest = {"id": threats[0].id, "dist": threats[0].dist}

	var snap = {
		"wave": RunData.current_wave,
		"wave_time": int(main._wave_timer.wait_time - main._wave_timer.time_left),
		"hp": int(player.current_stats.health),
		"max_hp": int(player.max_stats.health),
		"gold": RunData.get_player_gold(0),
		"enemies": spawner.enemies.size(),
		"projectiles": proj_count,
		"nearest_threat": nearest,
		"heading": _vec(heading),
		# null unless the arbiter steered this tick (see below)
		"margin": null,
		# BOTato tuning fields
		"pos": _pos(player.position),
		"near_e": int(near_enemy),
		"charging": charging,
		"corr": corr,
		"edge": int(edge),
		"dmg_w": int(_damage_taken_this_wave),
		"esc": esc,
		"bosses": bosses,
	}

	# Arbiter runs: esc bits are meaningless (it has no subsystems), so record
	# the decision itself — chosen heading and how much better it scored than
	# the runner-up. A margin near zero every tick means the action space is
	# too coarse or the weights are not separating candidates.
	if move_behavior and ("arbiter_active" in move_behavior) and move_behavior.arbiter_active:
		var arb = move_behavior._arbiter
		var margin = 0.0
		var chosen = Vector2.ZERO
		if arb:
			chosen = arb.last_dir
			# Margin against the best CLEARLY DIFFERENT heading (>45 deg away).
			# Comparing to the overall runner-up says nothing: the refinement
			# candidates sit 11 deg off the winner and are near-ties by
			# construction. What matters is how strongly one region of the
			# compass is preferred over another.
			var best = 1e18
			for s in arb.last_scores:
				if s < best:
					best = s
			var rival = 1e18
			for i in range(arb.last_scores.size()):
				var d = arb.last_dirs[i]
				if d == Vector2.ZERO or chosen == Vector2.ZERO or d.dot(chosen) > 0.7:
					continue
				if arb.last_scores[i] < rival:
					rival = arb.last_scores[i]
			if rival < 1e17:
				margin = rival - best
		# eff is path efficiency over the last second: 1.0 = held a heading,
		# low = the decision oscillated and most of the movement cancelled out.
		var hs = [0.0, 0.0, 0, 0, 0, 0, 0]
		if move_behavior.has_method("take_heading_stats"):
			hs = move_behavior.take_heading_stats()
			while hs.size() < 7:
				hs.push_back(0)
		# pesc/pfire, NOT esc/fires: the snapshot already carries esc for the
		# non-arbiter path, and a shared name would conflate the two (the
		# pillar-vs-orbiter proj(v=0) collision that cost a cycle).
		var pesc = 0
		var pfire = 0
		var sok = -1                 # fire_still stand permission at sample time; -1 = n/a
		if arb and arb.get("last_escaping") != null:
			pesc = 1 if arb.last_escaping else 0
			pfire = int(arb.pin_fires)
			if arb.get("last_stand_ok") != null:
				sok = 1 if arb.last_stand_ok else 0
		var eng = 0.0
		if arb and arb.get("last_engage") != null:
			eng = float(arb.last_engage)  # resolved contact-seeking weight this frame (0 = disarmed)
		var anc = -1
		if arb and arb.get("last_anchor_dist") != null:
			anc = int(arb.last_anchor_dist)   # px to the profile anchor (-1 = none)
		var dtg = -1
		var tswitch = 0
		var tkind = "none"
		var tdrop = 0
		if arb and arb.get("last_target_dist") != null:
			dtg = int(arb.last_target_dist)    # px to committed collectible (-1 = none)
			tswitch = int(arb.target_switches)
			tkind = str(arb.last_target_kind)
			tdrop = int(arb.target_threat_drops)
		var us = -1
		if move_behavior.get("last_arb_us") != null:
			us = int(move_behavior.last_arb_us)   # steering cost this tick, microseconds
		var hop = 0
		if arb and arb.get("last_hop") != null and arb.last_hop:
			hop = 1                                # the chosen move is a half-speed hop
		var stand = 0
		if arb and arb.get("last_stand") != null:
			stand = int(arb.last_stand)            # standing income, points per second
		var eblk = "-"
		if move_behavior.get("_world") != null and move_behavior._world != null \
				and move_behavior._world.get("last_engage_block") != null:
			eblk = str(move_behavior._world.last_engage_block)   # why engage resolved to 0
		snap.heading = _vec(chosen)
		snap.margin = stepify(margin, 0.01)
		snap.arb = {
			"eff": hs[0], "turn": hs[1], "flips": hs[2], "frames": hs[3], "still": hs[4],
			"pesc": pesc, "pfire": pfire, "sok": sok, "eng": int(eng), "eblk": eblk,
			"anc": anc, "dtg": dtg, "tswitch": tswitch, "us": us, "hop": hop, "stand": stand,
			"tkind": tkind, "tdrop": tdrop,
			"ticks": hs[5], "breaks": hs[6]}

	snap.mats = materials(player.position)
	snap.loot = loot_snapshot(player.position)

	rec.snapshot(snap)
	var rt = get_node_or_null("/root/BotRuntime")
	if rt != null:
		rt.push_snapshot(snap)


# main._active_golds includes attracted pickups until on_gold_picked_up erases
# them (.decompiled/main.gd:772,832). Match world_view's attracted_by exclusion
# for unattached only; count/value/nearest still describe the whole floor.
func materials(origin: Vector2) -> Dictionary:
	var pickups = []
	for g in get_parent()._active_golds:
		if is_instance_valid(g) and not g.already_picked_up:
			pickups.append({"position": g.position, "value": g.value,
				"unattached": g.attracted_by == null})
	return RunRecorder.mats(pickups, origin, RunData.bonus_gold)


# Called by main.gd from _on_player_died, synchronously, before the game cleans
# up the room. killer is the id main.gd read off the DieArgs ("" when unknown;
# the last recorded damage source is used instead).
func record_death(player, killer):
	var rec = _recorder()
	if rec == null or player == null or not is_instance_valid(player):
		return
	var main = get_parent()
	var threats = _nearby_threats(main, player, 3)
	if threats.empty():
		threats = _last_threats
	var ids = []
	for t in threats:
		ids.push_back(t.id)
	if killer == "":
		killer = _last_damage_src
	_last_killer = killer
	var build = _build()
	rec.event("death", {
		"wave": RunData.current_wave,
		"position": _pos(player.position),
		"killer": killer,
		"last_threats": ids,
		"build": build,
		"dmg_w": int(_damage_taken_this_wave),
	})


# The "build" event main.gd writes at run end for both outcomes.
func record_build():
	var rec = _recorder()
	if rec != null:
		rec.event("build", _build())


func _build() -> Dictionary:
	var weapons = []
	for w in RunData.get_player_weapons(0):
		weapons.push_back(w.my_id)
	var items = []
	for it in RunData.get_player_items(0):
		items.push_back(it.my_id)
	return RunRecorder.build_event(weapons, items)


# The killer written into the last death event ("" before any death), for
# main.gd's completion gate.
func last_killer() -> String:
	return _last_killer


# Damage taken by player 0 this wave, for main.gd's wave_end event.
func damage_taken_this_wave() -> int:
	return int(_damage_taken_this_wave)


func _esc_bits(move_behavior) -> int:
	var esc = 0
	if move_behavior:
		if ("escaping" in move_behavior) and move_behavior.escaping:
			esc += 1
		if ("countering" in move_behavior) and move_behavior.countering:
			esc += 2
		if ("crossfiring" in move_behavior) and move_behavior.crossfiring:
			esc += 4
		if ("aoe_fleeing" in move_behavior) and move_behavior.aoe_fleeing:
			esc += 8
		if ("dodging" in move_behavior) and move_behavior.dodging:
			esc += 16
		if ("proj_dodging" in move_behavior) and move_behavior.proj_dodging:
			esc += 32
		if ("pillar_navigating" in move_behavior) and move_behavior.pillar_navigating:
			esc += 64
		if ("cautious" in move_behavior) and move_behavior.cautious:
			esc += 128
		if ("wall_lapping" in move_behavior) and move_behavior.wall_lapping:
			esc += 256
	return esc


func _hook_player(player):
	if _hooked_player == player:
		return
	_hooked_player = player
	var _err = player.connect("took_damage", self, "_on_player_took_damage")


func _on_player_took_damage(unit, value, _kb, _is_crit, is_dodge, is_protected, _armor, args, _hit_type, _one_shot):
	if not _bot_active():
		return
	if is_dodge or is_protected:
		return
	_damage_taken_this_wave += value
	var rec = _recorder()
	# The player's health is already reduced when took_damage fires (unit.gd
	# subtracts before emitting), so this is the health after the hit.
	var ev = {"wave": RunData.current_wave, "source": "?", "amount": int(value),
			"hp_after": int(unit.current_stats.health),
			"total_this_wave": int(_damage_taken_this_wave)}
	# Classify the source NOW — the TakeDamageArgs instance is reused by the
	# engine, so it is only valid synchronously inside this handler. hit_type
	# is useless here (always NORMAL for the player); the hitbox owner isn't.
	var src = "?"
	if args and args.hitbox:
		var hb_parent = args.hitbox.get_parent()
		if hb_parent is Projectile:
			# A Pivot-mounted orbiter never sets `velocity`, so it reads as
			# proj(v=0) -- indistinguishable from an invoker pillar, which makes
			# the two impossible to separate in a sweep. Label it by its parent.
			if hb_parent.get_parent() is Pivot:
				src = "orbiter"
			# v~0 = pillar/AoE; a just-stopped bullet may also read 0, so record
			# the number instead of guessing a label
			else:
				src = "proj(v=%d)" % int(hb_parent.velocity.length())
			# Frame-accurate impact geometry: the 1 Hz tick misses sub-second
			# dodge commits, so record what the bot was DOING at this instant
			if rec != null and _hooked_player and is_instance_valid(_hooked_player) and not _hooked_player.dead:
				_add_hit_detail(ev, hb_parent)
		elif args.from != null and ("enemy_id" in args.from):
			src = args.from.enemy_id
		elif hb_parent != null and ("enemy_id" in hb_parent):
			src = hb_parent.enemy_id
	_last_damage_src = src
	if rec == null:
		return
	ev.source = src
	rec.event("damage", ev)


# PHIT / PCHOICE / PHIST detail for a projectile hit, added to the damage event
# as its hit, choice and hist keys.
func _add_hit_detail(ev, hb_parent):
	var mb = _hooked_player._movement_behavior
	var mv = Vector2.ZERO
	if mb and ("last_move_dir" in mb):
		mv = mb.last_move_dir
	var bv = hb_parent.velocity
	var hit = {"ppos": _pos(_hooked_player.position), "bv": _pos(bv),
			"esc": _esc_bits(mb), "mv": _vec(mv)}
	# Stationary telegraphs: the clock the world-view reads off the projectile's
	# AnimationPlayer decides when it is priced as armed, so record that clock
	# at the moment it actually hit.
	var telegraph = false
	if bv.length_squared() < 100.0 and ("_animation_player" in hb_parent) \
			and hb_parent._animation_player != null:
		var ap = hb_parent._animation_player
		telegraph = true
		hit.anim = ap.current_animation
		hit.anim_pos = stepify(ap.current_animation_position, 0.01)
		hit.playing = 1 if ap.is_playing() else 0
		hit.ppdist = int(_hooked_player.position.distance_to(hb_parent.global_position))
	ev.hit = hit
	# The scorer's own numbers for the decision that walked into a telegraph:
	# the six cheapest candidates [bearing deg or "Z", cost] and what standing
	# still cost; hop = the chosen move was a half-speed hop.
	if telegraph and mb and ("_arbiter" in mb) and mb._arbiter != null \
			and mb._arbiter.get("last_scores") != null:
		var arb = mb._arbiter
		var order = []
		for i in range(arb.last_scores.size()):
			order.push_back(i)
		_sort_scores = arb.last_scores
		order.sort_custom(self, "_score_less")
		var best = []
		for k in range(min(6, order.size())):
			var i = order[k]
			var d = arb.last_dirs[i]
			var tag = "Z" if d == Vector2.ZERO else str(int(rad2deg(d.angle())))
			best.push_back([tag, int(arb.last_scores[i])])
		var zero = arb.last_scores[24] if arb.last_scores.size() > 24 else -1.0
		ev.choice = {"best": best, "still": int(zero), "hop": 1 if arb.last_hop else 0}
		# ...and the decisions of the previous ~0.6 s that walked here:
		# [ms ago, x, y, bearing ("Z" = stand), best, still, aoe, hop]
		if mb.get("decision_hist") != null and mb.decision_hist.size() > 0:
			var now = OS.get_ticks_msec()
			var rows = []
			for h in mb.decision_hist:
				rows.push_back([now - h[0], h[1], h[2],
						"Z" if h[3] == -999 else str(h[3]), h[4], h[5], h[6], h[7]])
			ev.hist = rows


func _nearest_distance(units, pos) -> float:
	var best = 99999.0
	for u in units:
		if u.dead or u._pending_die:
			continue
		var d = u.position.distance_to(pos)
		if d < best:
			best = d
	return best


func _count_charging(units, _pos) -> int:
	var n = 0
	for u in units:
		if u.dead or u._pending_die:
			continue
		if u._current_attack_behavior is ChargingAttackBehavior:
			if u._move_locked or not u._can_move:
				n += 1
	return n


class _ByDistance:
	static func sort(a, b) -> bool:
		return a[0] < b[0]


# The count nearest live enemies and bosses as [{id, dist}], nearest first.
func _nearby_threats(main, player, count) -> Array:
	var all = []
	for u in main._entity_spawner.enemies + main._entity_spawner.bosses:
		if not is_instance_valid(u) or u.dead:
			continue
		all.push_back([u.position.distance_to(player.position), u.enemy_id])
	# Plain sort() on [float, String] pairs triggers "bad comparison function"
	# console spam; compare distances only
	all.sort_custom(_ByDistance, "sort")
	var out = []
	for i in range(min(count, all.size())):
		out.push_back({"id": all[i][1], "dist": int(all[i][0])})
	return out


func _pos(v) -> Array:
	return [int(v.x), int(v.y)]


func _vec(v) -> Array:
	return [stepify(v.x, 0.01), stepify(v.y, 0.01)]


var _sort_scores = []
func _score_less(a, b) -> bool:
	return _sort_scores[a] < _sort_scores[b]
