extends Reference
# What a human pause means for the bot's coroutines. Pure logic (static funcs)
# so it runs in the headless test project; BotRuntime and the shop / level-up
# extensions call it with live values. No class_name -- callers preload this.
#
# Ruling (final review C1/C2/I1): a bot coroutine re-checks may_continue after
# every yield; during a bot decision pause ESC means "stop waiting, the rules
# decide" and a move key means "stop waiting, then halt (human input)"; the bot
# never unpauses the tree under an open pause menu.

# Relative preload: resolves in the game and in the headless test project.
const Guards = preload("guards.gd")

const ESCAPE_ACTIONS = ["ui_pause", "ui_cancel"]


# May a bot coroutine act after a yield?
#   may_act        BotRuntime.may_act() (bot acting/deciding on the bot profile)
#   tree_paused    get_tree().paused
#   bot_state      BotRuntime.bot_state
#   human_paused   BotRuntime.human_paused (Ellie paused since this shop visit
#                  or decision started, and decide() did not consume it)
# False when the bot may not act, when the tree is paused by anyone but
# decide() itself, or when Ellie paused: she finishes this screen by hand.
static func may_continue(may_act, tree_paused, bot_state, human_paused) -> bool:
	if not may_act or human_paused:
		return false
	if tree_paused and str(bot_state) != "deciding":
		return false
	return true


# Should decide() unpause the tree when it stops waiting? Only when decide()
# paused it (the tree was not paused before) and no pause menu is open: a
# pause menu Ellie opened stays hers.
static func unpause_after_decide(was_paused, pause_menu_open) -> bool:
	return not was_paused and not pause_menu_open


# Classifies an input event that arrives while a decision is pending:
#   "escape"  ui_pause / ui_cancel released (the game opens its pause menu on
#             release: decompiled base_shop.gd:215-222, pause_menu.gd:34)
#   "move"    Guards.is_human_move with move_scancodes (any pressed joypad
#             button counts, so a pad's B press is a move); the mouse is
#             ignored: the tree is paused and she may be using the menu
#   ""        anything else
static func deciding_input(event, move_scancodes) -> String:
	if event == null:
		return ""
	for action in ESCAPE_ACTIONS:
		if InputMap.has_action(action) and event.is_action_released(action):
			return "escape"
	if Guards.is_human_move(event, move_scancodes, null, false):
		return "move"
	return ""
