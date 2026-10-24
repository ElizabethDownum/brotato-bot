extends Reference
# The launch request the harness writes to user://brotato-bot/launch.json
# (`prepare`): the mod reads it once, presses through the run-start screens and
# deletes it. Pure logic -- no game autoloads -- so it runs in the headless test
# project. No class_name; callers preload this script.
#
# File shape (all six keys required):
#   {"token": str, "character_id": "character_old",
#    "starting_weapon": "weapon_rock" | "any", "danger": 0..5,
#    "target_challenge": str, "created_at": str}

const BotPaths = preload("bot_paths.gd")

const DEFAULT_PATH = BotPaths.ROOT + "/launch.json"
const STRING_KEYS = ["token", "character_id", "starting_weapon", "target_challenge", "created_at"]
const MAX_DANGER = 5


# The launch dictionary (danger converted to int), or null for a missing file,
# bad JSON, a missing or ill-typed key, or danger outside 0..5.
static func load_from(path):
	var f = File.new()
	if not f.file_exists(path) or f.open(path, File.READ) != OK:
		return null
	var text = f.get_as_text()
	f.close()
	return parse(text)


static func parse(text):
	var parsed = JSON.parse(text)
	if parsed.error != OK or typeof(parsed.result) != TYPE_DICTIONARY:
		return null
	var d = parsed.result
	for k in STRING_KEYS:
		if typeof(d.get(k)) != TYPE_STRING:
			return null
	var danger = d.get("danger")
	if typeof(danger) != TYPE_REAL and typeof(danger) != TYPE_INT:
		return null
	if danger != floor(danger) or danger < 0 or danger > MAX_DANGER:
		return null
	d.danger = int(danger)
	return d


# The WeaponData my_id values to look for among the starting-weapon elements, in
# order. The starting weapons are the tier-1 resources ("weapon_rock_1", their
# weapon_id is "weapon_rock"), so the per-tier form goes first, then the bare id.
static func weapon_candidates(id: String) -> Array:
	return [id + "_1", id]


# DifficultyData.my_id for a danger level: items/difficulties/<n>/difficulty_<n>.tres.
static func difficulty_id(danger: int) -> String:
	return "difficulty_%d" % danger
