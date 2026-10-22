extends Reference
# Safety guards that keep the bot off the owner's own save profile and hand
# control back the instant a human touches the move controls. Pure logic: every
# function takes explicit inputs so it runs in the headless test project (no
# ProgressData, no /root/AutobattlerOptions). Callers preload this script.

const MOVE_ACTIONS = ["move_left", "move_right", "move_up", "move_down"]

# Used when the InputMap has none of MOVE_ACTIONS (the headless test project).
const FALLBACK_MOVE_SCANCODES = [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT]

# Left stick (0, 1) and right stick (2, 3); triggers (6, 7) are not movement.
const MOVE_AXES = [0, 1, 2, 3]
const AXIS_THRESHOLD = 0.5


# True only when the game's current profile is the configured bot profile.
static func profile_ok(current_profile_id, config) -> bool:
	return int(current_profile_id) == int(config.get("bot_profile_id", 1))


static func plan_present(path) -> bool:
	return File.new().file_exists(path)


# The game must keep running when the window loses focus while the bot plays.
static func focus_setting_ok(settings) -> bool:
	return settings.get("pause_on_focus_lost", true) == false


# "" when the bot may be enabled, else the refusal reason (profile first).
static func enable_refusal(current_profile_id, config, plan_path) -> String:
	if not profile_ok(current_profile_id, config):
		return "wrong profile (%d)" % int(current_profile_id)
	if not plan_present(plan_path):
		return "no plan at %s" % plan_path
	return ""


# Scancodes bound to the move actions in the live InputMap, or the fallback set.
static func default_move_scancodes() -> Array:
	var codes = []
	for action in MOVE_ACTIONS:
		if not InputMap.has_action(action):
			continue
		for ev in InputMap.get_action_list(action):
			if ev is InputEventKey:
				if ev.scancode != 0 and not codes.has(ev.scancode):
					codes.append(ev.scancode)
				if ev.physical_scancode != 0 and not codes.has(ev.physical_scancode):
					codes.append(ev.physical_scancode)
	if codes.empty():
		return FALLBACK_MOVE_SCANCODES.duplicate()
	return codes


# A pressed move key or a stick pushed past the threshold. Mouse is ignored.
static func is_human_move(event, move_scancodes = null) -> bool:
	if event is InputEventKey:
		if not event.pressed:
			return false
		var codes = move_scancodes if move_scancodes != null else default_move_scancodes()
		return codes.has(event.scancode) or (event.physical_scancode != 0 and codes.has(event.physical_scancode))
	if event is InputEventJoypadMotion:
		return MOVE_AXES.has(event.axis) and abs(event.axis_value) > AXIS_THRESHOLD
	return false
