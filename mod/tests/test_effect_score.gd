extends "res://mod/tests/test_base.gd"

const EffectScore = preload("res://mod/Ellie-BrotatoBot/shopping/effect_score.gd")


func _fx(key, value):
	return {"key": key, "value": value}


func test_tier1_sized_effect_scores_exactly_the_weight():
	assert_eq(EffectScore.score([_fx("stat_speed", 3)], {"stat_speed": 7.0}, {}, false), 7.0, "speed +3")
	assert_eq(EffectScore.score([_fx("stat_range", 15)], {"stat_range": 2.0}, {}, false), 2.0, "range +15")


func test_magnitude_scales_linearly():
	var got = EffectScore.score([_fx("stat_speed", -10)], {"stat_speed": -14.0}, {}, false)
	assert_true(abs(got - 46.6666666667) < 1e-6, "got %s" % str(got))


func test_cap_binds():
	assert_eq(EffectScore.score([_fx("stat_range", 300)], {"stat_range": 2.0}, {}, false), 8.0, "capped at 4 units")


func test_negative_value_on_positive_weight_subtracts():
	assert_eq(EffectScore.score([_fx("stat_armor", -2)], {"stat_armor": 4.0}, {}, false), -8.0, "armor -2")


func test_unweighted_key_scores_zero():
	assert_eq(EffectScore.score([_fx("stat_luck", 5)], {"stat_armor": 4.0}, {}, false), 0.0, "luck unweighted")


func test_boost_multiplier_applies():
	assert_eq(EffectScore.score([_fx("stat_dodge", 3)], {"stat_dodge": 3.0}, {"stat_dodge": 2.0}, false), 6.0, "boosted")


func test_harvest_cap_applies():
	var got = EffectScore.score([_fx("stat_harvesting", 5)], {"stat_harvesting": 10.0}, {}, true)
	assert_true(abs(got - 1.5) < 1e-6, "got %s" % str(got))
	assert_eq(EffectScore.score([_fx("stat_armor", 1)], {"stat_armor": 4.0}, {}, true), 4.0, "cap only harvesting")


func test_null_effect_is_skipped_and_zero_value_adds_nothing():
	var fx = [null, _fx("stat_armor", 0), _fx("stat_armor", 1)]
	assert_eq(EffectScore.score(fx, {"stat_armor": 4.0}, {}, false), 4.0, "null and zero skipped")


func test_every_unit_is_positive():
	var bad = 0
	for k in EffectScore.UNITS:
		if not EffectScore.UNITS[k] > 0.0:
			bad += 1
	assert_eq(bad, 0, "non-positive units")
	assert_true(EffectScore.UNITS.size() > 0, "has units")
