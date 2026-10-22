extends Reference
# Bot configuration read from user://brotato-bot/config.json. Pure logic: every
# function takes an explicit path so it runs in the headless test project.
# No class_name -- callers preload this script (see shopping/build_plans.gd).
#
# load_from(path) returns DEFAULTS merged with whatever keys the file provides.
# Unknown keys in the file are kept (harmless); defaults are never removed. A
# missing, unreadable or invalid file yields the defaults alone.
#
# Types after load:
#   int:    bot_profile_id, request_timeout_ms, checkpoint_timeout_ms
#           (JSON numbers parse as floats; these are converted with int())
#   float:  ask_tie_margin, ask_floor
#   String: target_challenge, export_hotkey

const DEFAULT_PATH = "user://brotato-bot/config.json"

const DEFAULTS = {
	"bot_profile_id": 1,
	"request_timeout_ms": 45000,
	"checkpoint_timeout_ms": 120000,
	"ask_tie_margin": 3.0,
	"ask_floor": 8.0,
	"target_challenge": "",
	"export_hotkey": "F9",
}

const INT_KEYS = ["bot_profile_id", "request_timeout_ms", "checkpoint_timeout_ms"]
const FLOAT_KEYS = ["ask_tie_margin", "ask_floor"]


static func load_from(path):
	var cfg = DEFAULTS.duplicate(true)
	var f = File.new()
	if not f.file_exists(path):
		return cfg
	if f.open(path, File.READ) != OK:
		push_warning("BotConfig: cannot open %s; using defaults" % path)
		return cfg
	var text = f.get_as_text()
	f.close()
	var parsed = JSON.parse(text)
	if parsed.error != OK:
		push_warning("BotConfig: invalid JSON in %s (line %d: %s); using defaults"
			% [path, parsed.error_line, parsed.error_string])
		return cfg
	if typeof(parsed.result) != TYPE_DICTIONARY:
		push_warning("BotConfig: %s is not a JSON object; using defaults" % path)
		return cfg
	for k in parsed.result.keys():
		cfg[k] = parsed.result[k]
	for k in INT_KEYS:
		var v = cfg[k]
		if typeof(v) == TYPE_REAL or typeof(v) == TYPE_INT:
			cfg[k] = int(v)
		else:
			push_warning("BotConfig: %s must be a number; using default" % k)
			cfg[k] = DEFAULTS[k]
	for k in FLOAT_KEYS:
		var v = cfg[k]
		if typeof(v) == TYPE_REAL or typeof(v) == TYPE_INT:
			cfg[k] = float(v)
		else:
			push_warning("BotConfig: %s must be a number; using default" % k)
			cfg[k] = DEFAULTS[k]
	return cfg
