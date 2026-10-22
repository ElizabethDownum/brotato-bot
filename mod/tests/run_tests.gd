extends SceneTree

# Headless runner: godot --path . --no-window --script mod/tests/run_tests.gd
# Loads every res://mod/tests/test_*.gd, calls each test_* method, prints
# PASS/FAIL per method and an "N passed, M failed" summary, exits 1 on failure.
# A method that makes no assert_* call fails ("no assertions").

const TEST_DIR = "res://mod/tests"


func _init():
	var passed = 0
	var failed = 0

	var files = _list_test_files()
	if files.empty():
		print("FAIL no test files found in %s" % TEST_DIR)
		failed += 1

	for path in files:
		var script = load(path)
		if script == null or not script.can_instance():
			print("FAIL %s: script failed to load" % path)
			failed += 1
			continue
		var inst = script.new()
		if not "failures" in inst:
			print("FAIL %s: does not extend test_base.gd" % path)
			failed += 1
			continue
		for name in _test_methods(inst):
			inst.failures = []
			inst.assertions = 0
			inst.call(name)
			if inst.failures.empty() and inst.assertions == 0:
				# Also what a test that hit a runtime error before its first
				# assertion looks like (Godot 3 cannot catch it).
				inst.failures.append("no assertions")
			if inst.failures.empty():
				print("PASS %s" % name)
				passed += 1
			else:
				print("FAIL %s: %s" % [name, PoolStringArray(inst.failures).join("; ")])
				failed += 1

	print("%d passed, %d failed" % [passed, failed])
	quit(1 if failed > 0 else 0)


func _list_test_files():
	var files = []
	var dir = Directory.new()
	if dir.open(TEST_DIR) != OK:
		return files
	dir.list_dir_begin(true, true)
	var f = dir.get_next()
	while f != "":
		if not dir.current_is_dir() and f.begins_with("test_") and f.ends_with(".gd") and f != "test_base.gd":
			files.append(TEST_DIR + "/" + f)
		f = dir.get_next()
	dir.list_dir_end()
	files.sort()
	return files


func _test_methods(inst):
	var names = []
	for m in inst.get_method_list():
		var n = m["name"]
		if n.begins_with("test_") and not names.has(n):
			names.append(n)
	names.sort()
	return names
