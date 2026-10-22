extends "res://main.gd"

const AICanvas  = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_canvas.gd")
const AITelemetry = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/ai_telemetry.gd")
const CoopFocusHud = preload("res://mods-unpacked/Ellie-BrotatoBot/extensions/coop_focus_hud.gd")
const BuildPlans = preload("res://mods-unpacked/Ellie-BrotatoBot/shopping/build_plans.gd")

var canvas_layer
var ai_telemetry
var coop_focus_hud

func _ready():
	canvas_layer = AICanvas.new()
	add_child(canvas_layer)
	ai_telemetry = AITelemetry.new()
	add_child(ai_telemetry)
	coop_focus_hud = CoopFocusHud.new()
	add_child(coop_focus_hud)
	if has_signal("end_of_the_wave"):
		connect("end_of_the_wave", self, "_on_bot_end_of_the_wave")

# Re-check plan.json's mtime at wave end so an edited plan is seen by the
# level-up picks and the shop (the shop also re-checks via BuildPlans.get_plan).
func _on_bot_end_of_the_wave() -> void:
	BuildPlans.refresh_plan_file()

func free():
	remove_child(canvas_layer)
	.free()
