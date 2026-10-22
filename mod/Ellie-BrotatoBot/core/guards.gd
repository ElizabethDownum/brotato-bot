extends Reference
# Safety guards that keep the bot off the owner's own save profile and hand
# control back the instant a human touches the move controls. Pure logic: every
# function takes explicit inputs so it runs in the headless test project (no
# ProgressData, no /root/AutobattlerOptions). Callers preload this script.

# The game's own move bindings (keys + d-pad buttons; analog_move_* are axes).
const MOVE_ACTIONS = ["button_move_left", "button_move_right", "button_move_up", "button_move_down"]

# Used when the InputMap has none of MOVE_ACTIONS (the headless test project).
# Mirrors the game's bindings: WASD, arrows, IJKL.
const FALLBACK_MOVE_SCANCODES = [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
		KEY_I, KEY_J, KEY_K, KEY_L]

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
# Callers cache the result (BotRuntime.move_scancodes()); it walks the InputMap.
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


# True when a human is touching the controls:
#   - a pressed move key (echo included: a held key counts), by scancode or
#     physical_scancode; move_scancodes null means default_move_scancodes()
#   - any pressed joypad button (move_buttons null), or one in move_buttons
#   - a stick axis 0..3 pushed past AXIS_THRESHOLD
#   - with mouse_only (the game's mouse-only control setting): mouse motion or
#     a pressed mouse button
# The Shift+Space toggle never reaches this (the caller returns first).
static func is_human_move(event, move_scancodes = null, move_buttons = null, mouse_only = false) -> bool:
	if event is InputEventKey:
		if not event.pressed:
			return false
		var codes = move_scancodes if move_scancodes != null else default_move_scancodes()
		return codes.has(event.scancode) or (event.physical_scancode != 0 and codes.has(event.physical_scancode))
	if event is InputEventJoypadButton:
		return event.pressed and (move_buttons == null or move_buttons.has(event.button_index))
	if event is InputEventJoypadMotion:
		return MOVE_AXES.has(event.axis) and abs(event.axis_value) > AXIS_THRESHOLD
	if mouse_only:
		if event is InputEventMouseMotion:
			return true
		if event is InputEventMouseButton:
			return event.pressed
	return false


# Run-completion outcome for BotRuntime.complete(): "win" or "death". Accepts the
# recorder's end-line word "won" as "win"; anything else counts as a death.
static func normalize_outcome(outcome) -> String:
	if outcome == "win" or outcome == "won":
		return "win"
	return "death"
