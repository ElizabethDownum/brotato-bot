extends Reference
# Stall rule for the level-up auto-pick loop's _process watchdog (final review
# M1). Measured in processed time, not frames and not wall time: at 134+ fps a
# 40-frame limit is shorter than PICK_WAIT (0.3 s) and reclaimed a healthy
# loop; wall time counted a human pause in Main (where UpgradesUI._process does
# not run) as a stall and reclaimed the loop on Resume (final re-review). The
# caller accumulates _process delta, which stands still exactly when the
# pause-aware pick timer does. Never a stall while the tree is paused.
# Pure logic; no class_name -- callers preload this script.

const STALL_MS = 1500


# True when the loop has made no progress for more than STALL_MS of processed time.
#   stall_ms  milliseconds of _process delta accumulated since the last progress
static func stalled(stall_ms, tree_paused) -> bool:
	if tree_paused:
		return false
	return int(stall_ms) > STALL_MS
