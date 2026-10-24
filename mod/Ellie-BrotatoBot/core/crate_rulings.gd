extends Reference
# Applied Haiku answers for one end-of-wave crate queue. Pure instance-local
# logic; a wave change clears every player's answers if the UI is retained.

var _wave = -1
var _players = {}


func _for_player(wave, pi) -> Dictionary:
	if wave != _wave:
		_wave = wave
		_players.clear()
	if not _players.has(pi):
		_players[pi] = {}
	return _players[pi]


func answer(wave, pi, item_id) -> Dictionary:
	return _for_player(wave, pi).get(item_id, {})


# Call only after the take/discard handler accepts a Haiku choice. Preserve
# the first decision id on reuse so every crate event links to its ruling.
func remember(wave, pi, item_id, action, decision_id) -> void:
	var ruled = _for_player(wave, pi)
	if action in ["take", "recycle"] and not ruled.has(item_id):
		ruled[item_id] = {"action": action, "id": decision_id}
