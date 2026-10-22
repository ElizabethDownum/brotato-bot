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


# Decision sources that explain a null answer without being a plain timeout
# (BotRuntime.decide: "interrupted" = a human unpaused the game, "invalid" = the
# response failed validation, "busy" = another decision was in flight).
const EXPLICIT_SOURCES = ["interrupted", "invalid", "busy"]


# What the checkpoint does with decide()'s result. response is its return
# value, source the decision event's source (last_decision.source), acting
# whether bot_state is "acting" after decide returned. Returns
# {applied: "revise_plan" | "skip" | "timeout", reason: String ("" when none)}:
#   source interrupted / invalid / busy  -> skip, reason = source
#   not acting (halted or completed)      -> skip, "halted" (nothing applied)
#   null response                         -> timeout
#   revise_plan with a plan_patch dict    -> revise_plan
#   anything else (skip, buy, ...)        -> skip
static func wanted(response, source, acting) -> Dictionary:
	if str(source) in EXPLICIT_SOURCES:
		return {"applied": "skip", "reason": str(source)}
	if not acting:
		return {"applied": "skip", "reason": "halted"}
	if response == null:
		return {"applied": "timeout", "reason": ""}
	if typeof(response) == TYPE_DICTIONARY and str(response.get("action", "")) == "revise_plan" 			and typeof(response.get("plan_patch")) == TYPE_DICTIONARY:
		return {"applied": "revise_plan", "reason": ""}
	return {"applied": "skip", "reason": ""}
