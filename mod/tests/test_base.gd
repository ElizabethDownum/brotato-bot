extends Reference

# Base class for test files: `extends "res://mod/tests/test_base.gd"`.
# The runner reads and clears `failures` around each test_* method.

var failures = []


# Type-strict: values must have the same typeof() too, so 1 != 1.0.
func assert_eq(a, b, msg = ""):
	if typeof(a) != typeof(b) or a != b:
		failures.append("expected %s == %s %s" % [str(a), str(b), msg])


func assert_true(x, msg = ""):
	if x != true:
		failures.append("expected true, got %s %s" % [str(x), msg])


func assert_false(x, msg = ""):
	if x != false:
		failures.append("expected false, got %s %s" % [str(x), msg])
