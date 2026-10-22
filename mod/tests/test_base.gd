extends Reference

# Base class for test files: `extends "res://mod/tests/test_base.gd"`.
# The runner reads and clears `failures` and `assertions` around each test_*
# method; a test that makes no assertion fails.

var failures = []
var assertions = 0


# Type-strict: values must have the same typeof() too, so 1 != 1.0.
func assert_eq(a, b, msg = ""):
	assertions += 1
	if typeof(a) != typeof(b) or a != b:
		failures.append("expected %s == %s %s" % [str(a), str(b), msg])


# Strict: only a bool true passes (1 does not).
func assert_true(x, msg = ""):
	assertions += 1
	if not (typeof(x) == TYPE_BOOL and x):
		failures.append("expected true, got %s %s" % [str(x), msg])


# Strict: only a bool false passes (0 and null do not).
func assert_false(x, msg = ""):
	assertions += 1
	if not (typeof(x) == TYPE_BOOL and not x):
		failures.append("expected false, got %s %s" % [str(x), msg])
