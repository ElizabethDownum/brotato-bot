extends Reference
# Target-challenge checkpoint rules. Pure logic (static funcs) so it runs in the
# headless test project; BotRuntime and extensions/main.gd do the game side.
# No class_name -- callers preload this script.
#
# When the target challenge completes mid-run, the bot pauses at the next wave
# end and asks the sidecar (decide("checkpoint", [])) whether to revise the plan.


# Does a completed challenge id match the target? An empty target matches nothing.
static func is_target(challenge_id, target_id) -> bool:
	return str(target_id) != "" and str(challenge_id) == str(target_id)


# Is the checkpoint due at this wave end? Once per run, after the target fired,
# and never on the final wave of a non-endless run: the completion gate
# (main.gd _bot_end_run) owns that wave end.
static func due(target_fired, checkpoint_done, current_wave, nb_of_waves, is_endless) -> bool:
	if not target_fired or checkpoint_done:
		return false
	if int(current_wave) >= int(nb_of_waves) and not is_endless:
		return false
	return true


# What a checkpoint response asks for: "timeout" (null: no valid answer),
# "revise_plan" (action revise_plan with a plan_patch dictionary) or "skip"
# (skip, and every other action, which means nothing at a checkpoint).
static func wanted(response) -> String:
	if response == null:
		return "timeout"
	if typeof(response) == TYPE_DICTIONARY and str(response.get("action", "")) == "revise_plan" \
			and typeof(response.get("plan_patch")) == TYPE_DICTIONARY:
		return "revise_plan"
	return "skip"
