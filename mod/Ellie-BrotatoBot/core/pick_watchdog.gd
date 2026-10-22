extends Reference
# Stall rule for the level-up auto-pick loop's _process watchdog (final review
# M1). Measured in wall time, not frames: at 134+ fps a 40-frame limit is
# shorter than PICK_WAIT (0.3 s) and reclaimed a healthy loop. Never a stall
# while the tree is paused: the pick wait is pause-aware and stands still.
# Pure logic; no class_name -- callers preload this script.

const STALL_MS = 1500


# True when the loop has made no progress for more than STALL_MS.
#   now_ms, last_progress_ms  OS.get_ticks_msec() values
static func stalled(now_ms, last_progress_ms, tree_paused) -> bool:
	if tree_paused:
		return false
	return int(now_ms) - int(last_progress_ms) > STALL_MS
