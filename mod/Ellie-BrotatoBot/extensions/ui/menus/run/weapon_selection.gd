extends "res://ui/menus/run/weapon_selection.gd"
# Mouse-driven co-op weapon selection, matching the character screen (shared logic
# in coop_mouse_select.gd):
#   * Click a player's panel to make that slot active (outlined in its color).
#   * Click a weapon in a player's inventory to pick it for them.
# The weapon screen has one inventory PER player with element signals bound to the
# inventory index, so a mouse pick routes to that column's player.
#
# It also keeps CoopService.listening_for_inputs true: the character screen runs
# with it on, but the weapon screen leaves it off, which makes each
# FocusEmulator._input swallow every mouse click before the weapon buttons or this
# node ever see it. It flips false naturally once all slots have picked.

const Coop = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ui/menus/run/coop_mouse_select.gd")
const BotRuntime = preload("res://mods-unpacked/Ellie-BrotatoBot/bot_runtime.gd")
const LaunchFile = preload("res://mods-unpacked/Ellie-BrotatoBot/core/launch_file.gd")

var _active_outline = null


func _ready() -> void:
	._ready()
	_active_outline = Coop.make_outline()
	add_child(_active_outline)
	Coop.enable_mouse_grid(self, RunData.is_coop_run)
	if RunData.is_coop_run:
		CoopService.listening_for_inputs = true
	call_deferred("_bot_launch_pick")


func _input(event: InputEvent) -> void:
	._input(event)
	if Coop.try_panel_click(self, event):
		get_tree().set_input_as_handled()


func _process(delta: float) -> void:
	._process(delta)
	Coop.update_outline(self, _active_outline)
	if RunData.is_coop_run and not _all_selected():
		CoopService.listening_for_inputs = true


# Back out of the launch with the screen: the previous screen would press again.
func _go_back() -> void:
	var rt = BotRuntime.instance()
	if rt != null and rt.pending_launch != null:
		rt.launch_cancel("Launch cancelled: back pressed")
	._go_back()


# Launcher: press the first existing starting-weapon element among the launch's
# candidates (the tier-1 my_id form first). "any" leaves the pick to the owner and
# the launch continues from the next screen.
func _bot_launch_pick() -> void:
	var rt = BotRuntime.instance()
	var launch = rt.launch_pick_step() if rt != null else null
	if launch == null:
		return
	if launch.starting_weapon == "any":
		rt.set_status("Launch: pick the starting weapon")
		return
	for id in LaunchFile.weapon_candidates(launch.starting_weapon):
		var element = _find_inventory_element_by_id(Keys.generate_hash(id), 0)
		if element != null:
			_on_element_pressed(element, 0)
			return
	rt.launch_cancel("Launch refused: weapon %s not available" % launch.starting_weapon)


func _all_selected() -> bool:
	for i in range(RunData.get_player_count()):
		if not _has_player_selected[i]:
			return false
	return true


func _set_base_ui_player_count(count: int, is_coop_run: bool, initialize: bool = false) -> void:
	._set_base_ui_player_count(count, is_coop_run, initialize)
	Coop.enable_mouse_grid(self, is_coop_run)


func _on_element_pressed(element: InventoryElement, inventory_player_index: int) -> void:
	Coop.route_to(element, inventory_player_index)
	._on_element_pressed(element, inventory_player_index)


func _on_element_focused(element: InventoryElement, inventory_player_index: int, displayPanelData: bool = true) -> void:
	# With bots present, a hover must not wipe an already-confirmed weapon: the base
	# focus handler unconditionally nulls _player_weapons[pi] and clears the selection.
	# Skip it for a slot that has already chosen -- a click still changes the pick.
	if Coop.only_p1_is_human():
		var pi = FocusEmulatorSignal.get_player_index(element)
		if pi >= 0 and pi < _player_weapons.size() and _player_weapons[pi] != null:
			return
	Coop.route_to(element, inventory_player_index)
	._on_element_focused(element, inventory_player_index, displayPanelData)
