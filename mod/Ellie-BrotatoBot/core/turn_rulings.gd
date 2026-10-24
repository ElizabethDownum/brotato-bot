extends Reference
# Applied Haiku verdicts for one turn: crates and the following shop visit.
# BotRuntime owns this pure store across scene changes, resetting at wave/run start.

var _wave = -1
var _players = {}


func reset(wave = -1) -> void:
	_wave = wave
	_players.clear()


func for_player(wave, pi) -> Dictionary:
	if wave != _wave:
		reset(wave)
	if not _players.has(pi):
		_players[pi] = {}
	return _players[pi]


func answer(wave, pi, item_id) -> Dictionary:
	return for_player(wave, pi).get(item_id, {})


# All rule acquisition paths use this gate, including carried locks and savings.
# Review-list items require approval even when no answer could be obtained.
static func rule_allowed(item_id, ask_on: Array, ruled: Dictionary) -> bool:
	var verdict = ruled.get(item_id, {}).get("verdict", "")
	return verdict != "decline" and (not ask_on.has(item_id) or verdict == "approve")


static func crate_fallback(item_id, ask_on: Array, score: float) -> String:
	return "take" if not ask_on.has(item_id) and score >= 0.0 else "recycle"


# Record a fresh shop answer against the ORIGINAL board, even after a reroll.
# Explicit declines apply independently of the main action; automatic review-list
# declines and pass require an applied action. Call only with a validated response.
# Return one original option index per declined id for unlock/reserve/event handling.
func shop_declines(wave, pi, ids: Array, ask_on: Array, response: Dictionary,
		decision_id: String, applied: String) -> Array:
	var act = response.action
	var oi = int(response.get("option_index", -1))
	var protected_id = ""
	if act in ["buy", "lock"] and oi >= 0 and oi < ids.size():
		protected_id = ids[oi]
	var indices = []
	for index in response.get("decline", []):
		if index < 0 or index >= ids.size():
			print("BOTLOG SHOP decline index=%s ignored=invalid decision=%s" % [str(index), decision_id])
		elif ids[index] == protected_id:
			print("BOTLOG SHOP decline index=%d ignored=%s-target decision=%s" % [index, act, decision_id])
		else:
			indices.append(index)
			print("BOTLOG SHOP decline index=%d item=%s decision=%s" % [index, ids[index], decision_id])
	if applied != "rule":
		for i in ids.size():
			if ids[i] != protected_id and (ask_on.has(ids[i]) or (act == "pass" and i == oi)):
				indices.append(i)
	var ruled = for_player(wave, pi)
	var declined = []
	var seen = {}
	for i in indices:
		var id = ids[i]
		if seen.has(id):
			continue
		seen[id] = true
		# A fresh veto is binding even if an earlier answer approved this id.
		# Reuse of an existing decline preserves its original provenance.
		if ruled.get(id, {}).get("verdict", "") != "decline":
			ruled[id] = {"verdict": "decline", "decision_id": decision_id, "screen": "shop"}
		declined.append(i)
	return declined


# Call only after an applied buy/pass/take/recycle. Locks have no verdict.
# Preserve the first decision's provenance when either screen reuses it.
func remember(wave, pi, item_id, verdict, decision_id, screen) -> void:
	var ruled = for_player(wave, pi)
	if verdict in ["approve", "decline"] and not ruled.has(item_id):
		ruled[item_id] = {"verdict": verdict, "decision_id": decision_id, "screen": screen}
