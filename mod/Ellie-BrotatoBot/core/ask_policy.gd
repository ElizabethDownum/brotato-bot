extends Reference
# Circuit breaker for sidecar decisions (final review I1). BotRuntime keeps
# one instance per run (reset at run start) and records every decide() source:
#   "timeout"             counts (no answer before the deadline; also a failed
#                         export / request write, or a halt while waiting)
#   "haiku" | "invalid"   an answer arrived: the count restarts
#   anything else         ("interrupted", "busy") neither counts nor resets
# After MAX_TIMEOUTS consecutive timeouts, asking stays off for the rest of
# the run (allowed() false): the rules decide with no request and no pause.
# Pure logic; no class_name -- callers preload this script.

const MAX_TIMEOUTS = 2
const WARNING = "sidecar timeouts; asking disabled for this run"

var timeouts = 0
var disabled = false


# Records one decision source; true only on the call that disables asking.
func record(source) -> bool:
	if disabled:
		return false
	var s = str(source)
	if s == "timeout":
		timeouts += 1
	elif s == "haiku" or s == "invalid":
		timeouts = 0
	if timeouts >= MAX_TIMEOUTS:
		disabled = true
		return true
	return false


func allowed() -> bool:
	return not disabled


func reset():
	timeouts = 0
	disabled = false
