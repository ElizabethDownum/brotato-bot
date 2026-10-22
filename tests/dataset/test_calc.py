# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
import math

import pytest

from brotato_bot.dataset.spud import calc


def test_cooldown_jitter_slow_weapon_single():
    # Shredder-like basis 45 frames, N=1: delta=min(45/5, 5)=5 -> [40, 50]
    lo, hi = calc.cooldown_jitter(45, 1)
    assert math.isclose(lo, 40.0)
    assert math.isclose(hi, 50.0)


def test_cooldown_jitter_slow_weapon_six_weapons():
    # basis 45, N=6: delta=min(6*45/5=54, 6*5=30)=30 -> [15, 75]
    lo, hi = calc.cooldown_jitter(45, 6)
    assert math.isclose(lo, 15.0)
    assert math.isclose(hi, 75.0)


def test_cooldown_jitter_fast_weapon_floors_at_one():
    # Minigun-like basis 3, N=6: delta=min(3.6, 30)=3.6; basis-delta=-0.6 -> floored to 1
    lo, hi = calc.cooldown_jitter(3, 6)
    assert math.isclose(lo, 1.0)
    assert math.isclose(hi, 6.6)


def test_cooldown_jitter_clamps_weapon_count_to_six():
    assert calc.cooldown_jitter(45, 99) == calc.cooldown_jitter(45, 6)


def test_cooldown_jitter_degenerate_basis_never_inverts():
    # No base-game weapon has a sub-1-frame cooldown, but a basis < 1 must not
    # yield an inverted (lo > hi) range once the low bound floors at 1.
    lo, hi = calc.cooldown_jitter(0, 6)
    assert lo <= hi
    assert lo == 1.0


def test_cadence_profile_minigun_sustained():
    # Minigun T4: cycle 0.09s, total_dps 55.5556 at rd0, basis 3 frames
    p = calc.cadence_profile(0.09, 55.5556, 3, weapon_count=1)
    assert math.isclose(p["attacks_per_second"], 1 / 0.09, rel_tol=1e-9)
    assert math.isclose(p["seconds_between_attacks"], 0.09)
    assert math.isclose(p["damage_per_attack"], 5.0, rel_tol=1e-4)  # base_damage 5
    assert p["cadence"] == "sustained"
    assert p["burst_reload"] is False
    # recoil_term = 0.09 - 3/60 = 0.04; N=1 jitter (2.4, 3.6)
    assert math.isclose(p["gap_range_s"][0], 0.04 + 2.4 / 60.0, rel_tol=1e-6)
    assert math.isclose(p["gap_range_s"][1], 0.04 + 3.6 / 60.0, rel_tol=1e-6)


def test_cadence_profile_shredder_bursty_and_invariant():
    # Shredder T4: cycle 1.05s, total_dps 23.8095 at rd0, basis 45 frames
    p = calc.cadence_profile(1.05, 23.8095, 45, weapon_count=1)
    assert p["cadence"] == "bursty"  # ~0.952 atk/s < 1
    assert math.isclose(p["damage_per_attack"], 25.0, rel_tol=1e-4)  # base_damage 25
    # Invariant: damage_per_attack * attacks_per_second == total_dps
    assert math.isclose(p["damage_per_attack"] * p["attacks_per_second"], 23.8095, rel_tol=1e-9)


def test_cadence_profile_moderate_label_boundary():
    # cycle 0.5s -> exactly 2 atk/s -> moderate
    assert calc.cadence_profile(0.5, 10.0, 30)["cadence"] == "moderate"
    # cycle exactly 1/3s -> 3 atk/s -> sustained (>= 3)
    assert calc.cadence_profile(1 / 3, 10.0, 20)["cadence"] == "sustained"


def test_cadence_profile_gap_range_widens_with_weapon_count():
    narrow = calc.cadence_profile(1.05, 23.8095, 45, weapon_count=1)["gap_range_s"]
    wide = calc.cadence_profile(1.05, 23.8095, 45, weapon_count=6)["gap_range_s"]
    assert wide[0] < narrow[0]
    assert wide[1] > narrow[1]


def test_cadence_profile_passes_burst_reload_flag():
    assert calc.cadence_profile(0.63, 90.0, 11, burst_reload=True)["burst_reload"] is True


def test_game_round_half_away_from_zero():
    # GDScript round(32.5) == 33, unlike Python's banker's rounding
    assert calc.game_round(32.5) == 33
    assert calc.game_round(62.5) == 63
    assert calc.game_round(-0.5) == -1
    assert calc.game_round(2.4) == 2


def test_game_int_truncates_toward_zero():
    assert calc.game_int(25.8) == 25
    assert calc.game_int(-3.7) == -3


def test_effective_cooldown_positive_as_divides():
    # weapon_service.gd:570-573 — max(MIN_COOLDOWN, cd / (1+as)) as int
    assert calc.effective_cooldown(60, 0.5) == 40
    assert calc.effective_cooldown(25, 0.12) == 22  # 22.32 truncates


def test_effective_cooldown_negative_as_multiplies():
    assert calc.effective_cooldown(60, -0.5) == 90


def test_effective_cooldown_two_frame_floor():
    assert calc.effective_cooldown(3, 2.0) == 2


def test_effective_cooldown_zero_as_passthrough():
    assert calc.effective_cooldown(60, 0.0) == 60


def test_ranged_cycle_pistol_t1_as0():
    # Pistol T1: recoil 0.1, cooldown 60 -> 2*0.1 + 60/60 = 1.2 (matches v5 dataset)
    assert calc.stat_aware_cycle_time(
        weapon_type="ranged", recoil_duration=0.1, cooldown=60, attack_speed_frac=0.0
    ) == pytest.approx(1.2)


def test_ranged_cycle_as_shrinks_recoil_and_cooldown():
    # AS +50%: recoil 0.1/1.5, cooldown max(2, 60/1.5)=40 -> 0.1333.. + 0.6667.. = 0.8
    assert calc.stat_aware_cycle_time(
        weapon_type="ranged", recoil_duration=0.1, cooldown=60, attack_speed_frac=0.5
    ) == pytest.approx(0.8)


def test_ranged_cycle_burst_reload_replaces_draw():
    # weapon.gd:337-339: every 6th draw is cd*mult INSTEAD of cd.
    # recoil 0.1, cd 12, every 6, mult 5: 0.2 + 12*((6-1)+5)/6/60 = 0.2 + 20/60
    assert calc.stat_aware_cycle_time(
        weapon_type="ranged",
        recoil_duration=0.1,
        cooldown=12,
        attack_speed_frac=0.0,
        burst=(6, 5.0),
    ) == pytest.approx(0.5333333333)


def test_melee_cycle_knife_t1_as0():
    # Knife T1: recoil 0.1, cd 25, max_range 150; default engagement min(150,70)=70
    # rf=70/70=1 -> atk=0.2+0.15=0.35; back=0.2; shooting=0.175+0.2+0.1=0.475
    # cycle = 0.475 + 25/60 = 0.891666..
    assert calc.stat_aware_cycle_time(
        weapon_type="melee", recoil_duration=0.1, cooldown=25, attack_speed_frac=0.0, max_range=150
    ) == pytest.approx(0.8916666667)


def test_melee_cycle_as100_triple_effect():
    # AS +100%: rf=70/clamp(70*(1+1/3),70,120)=0.75 -> atk=max(.01,.1)+0.1125=0.2125
    # back=0.2/4=0.05; recoil'=0.05; shooting=0.10625+0.05+0.05=0.20625
    # eff_cd=int(25/2)=12 -> cycle=0.20625+0.2=0.40625
    assert calc.stat_aware_cycle_time(
        weapon_type="melee", recoil_duration=0.1, cooldown=25, attack_speed_frac=1.0, max_range=150
    ) == pytest.approx(0.40625)


def test_melee_cycle_point_blank_override():
    # engagement_distance=0 -> rf=0 -> atk=0.2; shooting=0.1+0.2+0.1=0.4
    assert calc.stat_aware_cycle_time(
        weapon_type="melee",
        recoil_duration=0.1,
        cooldown=25,
        attack_speed_frac=0.0,
        max_range=150,
        engagement_distance=0.0,
    ) == pytest.approx(0.8166666667)


def test_stat_value_mapping():
    stats = {"melee_damage": 20, "damage": 30}
    assert calc.stat_value(stats, "stat_melee_damage") == 20
    assert calc.stat_value(stats, "stat_percent_damage") == 30  # irregular short name
    assert calc.stat_value(stats, "stat_levels", level=7) == 7
    assert calc.stat_value(stats, "stat_ranged_damage") == 0.0


def test_per_hit_damage_knife_t1_flat_scaling():
    # weapon_service.gd:489: max(1, 9 + 20*0.8) as int = 25
    assert calc.per_hit_damage(9, [["stat_melee_damage", 0.8]], {"melee_damage": 20}) == 25


def test_per_hit_damage_truncates_scaling_sum():
    # 9 + 21*0.8 = 25.8 -> truncates to 25 (same as md=20 — real steppiness)
    assert calc.per_hit_damage(9, [["stat_melee_damage", 0.8]], {"melee_damage": 21}) == 25


def test_per_hit_damage_percent_bracket_rounds_half_up():
    # d1=25; 25 * 1.30 = 32.5 -> GDScript round -> 33 (weapon_service.gd:249)
    assert (
        calc.per_hit_damage(9, [["stat_melee_damage", 0.8]], {"melee_damage": 20, "damage": 30})
        == 33
    )


def test_per_hit_damage_floors_at_one():
    # d1=9; 9 * 0.2 = 1.8 -> round 2; and at -100%: max(1, 0) -> 1
    assert calc.per_hit_damage(9, [["stat_melee_damage", 0.8]], {"damage": -80}) == 2
    assert calc.per_hit_damage(9, [["stat_melee_damage", 0.8]], {"damage": -100}) == 1


def test_expected_hit_damage_crit_expectation():
    # cc = 0.2 + 10/100 = 0.3; crit dmg round(32*2.5)=80
    # (1-0.3)*32 + 0.3*80 = 22.4 + 24 = 46.4
    assert calc.expected_hit_damage(32, 0.2, 2.5, player_crit_chance=10) == pytest.approx(46.4)


def test_expected_hit_damage_crit_clamped_to_certainty():
    # weapon 0.2 + player 200% -> clamp 1.0 -> always round(32*2.5)=80
    assert calc.expected_hit_damage(32, 0.2, 2.5, player_crit_chance=200) == pytest.approx(80.0)


KNIFE_T1 = {
    "weapon_type": "melee",
    "base_damage": 9.0,
    "cooldown": 25.0,
    "recoil_duration": 0.1,
    "attack_speed_mod": 0.0,
    "accuracy": 1.0,
    "crit_chance": 0.2,
    "crit_damage": 2.5,
    "max_range": 150.0,
    "scaling_stats": [["stat_melee_damage", 0.8]],
    "additional_cooldown_every_x_shots": -1,
    "additional_cooldown_multiplier": -1.0,
    "proc_effects": [],
}

PISTOL_T1 = {
    "weapon_type": "ranged",
    "base_damage": 12.0,
    "cooldown": 60.0,
    "recoil_duration": 0.1,
    "attack_speed_mod": 0.0,
    "accuracy": 0.9,
    "crit_chance": 0.1,
    "crit_damage": 2.0,
    "max_range": 400.0,
    "scaling_stats": [["stat_ranged_damage", 1.0]],
    "additional_cooldown_every_x_shots": -1,
    "additional_cooldown_multiplier": -1.0,
    "proc_effects": [],
}


def test_profile_knife_t1_melee_damage_20():
    # d2=25; expected = 0.8*25 + 0.2*round(62.5)=0.2*63 -> 32.6; ct=0.8916667
    p = calc.weapon_dps_profile(KNIFE_T1, {"melee_damage": 20})
    assert p["per_hit_damage"] == 25
    assert p["expected_hit_damage"] == pytest.approx(32.6)
    assert p["cycle_time"] == pytest.approx(0.8916666667)
    assert p["dps"] == pytest.approx(36.5607476636)
    assert p["engagement_distance_used"] == 70.0


def test_profile_pistol_t1_rd10_accuracy():
    # d2=22; expected = 0.9*22 + 0.1*round(44)=24.2; dps = 24.2/1.2*0.9 = 18.15
    p = calc.weapon_dps_profile(PISTOL_T1, {"ranged_damage": 10})
    assert p["dps"] == pytest.approx(18.15)
    assert p["engagement_distance_used"] is None


def test_profile_melee_dps_responds_to_melee_damage():
    lo = calc.weapon_dps_profile(KNIFE_T1, {})["dps"]
    hi = calc.weapon_dps_profile(KNIFE_T1, {"melee_damage": 50})["dps"]
    assert hi > lo  # the bug this project exists to fix


def test_profile_weapon_damage_proc():
    rec = dict(
        PISTOL_T1,
        proc_effects=[
            {"kind": "weapon_damage", "chance": 0.5, "enemies_hit": 1.0, "multiplier": 1.0}
        ],
    )
    p = calc.weapon_dps_profile(rec, {"ranged_damage": 10}, aoe_enemies_hit=2.0)
    assert p["base_dps"] == pytest.approx(18.15)
    # proc = base_dps * chance * (enemies_hit * aoe factor): 18.15 * 0.5 * 2.0
    assert p["proc_dps"] == pytest.approx(18.15)
    assert p["dps"] == pytest.approx(36.30)


def test_profile_burn_scales_with_elemental():
    rec = dict(
        PISTOL_T1,
        proc_effects=[
            {
                "kind": "burn_dot",
                "damage": 3.0,
                "scaling_stats": [["stat_elemental_damage", 1.0]],
                "tick_interval": 0.5,
            }
        ],
    )
    zero = calc.weapon_dps_profile(rec, {})
    ele = calc.weapon_dps_profile(rec, {"elemental_damage": 10})
    # tick dmg: max(1, 3+10)=13; %damage none -> 13/0.5 = 26 burn dps
    assert ele["proc_dps"] - zero["proc_dps"] == pytest.approx(26.0 - 6.0)


def test_profile_companion_proc():
    rec = dict(
        PISTOL_T1,
        proc_effects=[
            {
                "kind": "companion",
                "damage": 5.0,
                "scaling_stats": [["stat_elemental_damage", 1.0]],
                "crit_chance": 0.0,
                "crit_damage": 0.0,
                "count": 1.0,
                "enemies_hit": 2.0,
            }
        ],
    )
    p = calc.weapon_dps_profile(rec, {"elemental_damage": 5})
    # companion hit: max(1, 5+5)=10 -> expected 10 (no crit);
    # per host cycle (1.2s), accuracy 0.9 host hit-rate: 10*1*2/1.2*0.9 = 15
    assert p["proc_dps"] == pytest.approx(15.0)
