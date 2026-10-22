extends Reference
# The single game-side root for every file the mod reads or writes (config,
# plan, run recordings, probes). Godot's user:// is %APPDATA%\Brotato for the
# game. Steam Cloud measurement: learnings/steam-cloud.md.
# No class_name -- callers preload this script. Scripts under core/ preload it
# by a path relative to themselves so the same file resolves both in the game
# (res://mods-unpacked/...) and in the headless test project (res://mod/...).

const ROOT = "user://brotato-bot"
