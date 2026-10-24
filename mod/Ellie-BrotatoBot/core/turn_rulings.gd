extends Reference
const DecisionClient = preload("decision_client.gd")
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
# Explicit rulings apply even if the primary action cannot land. Missing review
# verdicts default to decline only after an applied answer. Missing counts are
# measured before action overrides. Return original indices for decline effects.
func shop_rulings(wave, pi, ids: Array, ask_on: Array, response: Dictionary,
		decision_id: String, applied: String) -> Dictionary:
	var oi = int(response.get("option_index", -1))
	var by_index = {}
	for entry in DecisionClient.normalize_rulings(response.get("rulings", []), ids.size()):
		by_index[entry.option_index] = entry.verdict
	var missing = ids.size() - by_index.size()
	print("BOTLOG SHOP rulings_missing=%d decision=%s" % [missing, decision_id])
	# The store is keyed by id: for conflicting copies decline wins, except
	# that an applied buy/pass wins for every copy of its target id.
	var verdicts = {}
	var indices = {}
	for i in ids.size():
		var verdict = by_index.get(i, "")
		if verdict == "" and applied != "rule" and ask_on.has(ids[i]):
			verdict = "decline"
		if verdict == "":
			continue
		var id = ids[i]
		if not verdicts.has(id) or (verdict == "decline" and verdicts[id] == "approve"):
			verdicts[id] = verdict
			indices[id] = i
	if applied in ["buy", "pass"] and oi >= 0 and oi < ids.size():
		var target_id = ids[oi]
		var action_verdict = "approve" if applied == "buy" else "decline"
		if (by_index.has(oi) and by_index[oi] != action_verdict) \
				or (verdicts.has(target_id) and verdicts[target_id] != action_verdict):
			print("BOTLOG SHOP ruling contradiction item=%s action=%s wins decision=%s" % [target_id, applied, decision_id])
		verdicts[target_id] = action_verdict
		indices[target_id] = oi
	var ruled = for_player(wave, pi)
	var declined = []
	for id in verdicts:
		ruled[id] = {"verdict": verdicts[id], "decision_id": decision_id, "screen": "shop"}
		if verdicts[id] == "decline":
			declined.append(indices[id])
	return {"declined": declined, "missing": missing}


# Single-choice acquisition record (crate take/recycle); shop boards instead use
# shop_rulings, including the explicit verdict on a lock target. Pure cache reuse
# preserves the first decision's provenance.
func remember(wave, pi, item_id, verdict, decision_id, screen) -> void:
	var ruled = for_player(wave, pi)
	if verdict in ["approve", "decline"] and not ruled.has(item_id):
		ruled[item_id] = {"verdict": verdict, "decision_id": decision_id, "screen": screen}
