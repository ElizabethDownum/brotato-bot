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


# Call only after an applied buy/pass/take/recycle. Locks have no verdict.
# Preserve the first decision's provenance when either screen reuses it.
func remember(wave, pi, item_id, verdict, decision_id, screen) -> void:
	var ruled = for_player(wave, pi)
	if verdict in ["approve", "decline"] and not ruled.has(item_id):
		ruled[item_id] = {"verdict": verdict, "decision_id": decision_id, "screen": screen}
