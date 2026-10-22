# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Pure DPS / merge math. No I/O — every function is unit-testable in isolation.

Game-exact DPS is computed per-stat-block by weapon_dps_profile() (below);
see docs/dps-engine.md. There is no closed-form line in ranged-damage (RD)
— callers that need DPS across an RD range (e.g. answers.compare_merge_paths)
sweep integer RD values and re-run the full profile at each point.
"""

from __future__ import annotations

import math


def cooldown_jitter(cooldown_basis_frames: float, weapon_count: int) -> tuple[float, float]:
    """Per-shot cooldown range (frames) from the engine's anti-sync randomization.

    Each shot draws cooldown uniformly from [max(1, basis - Δ), basis + Δ],
    Δ = min(N·basis/5, N·5), N = min(max(weapon_count, 1), 6) (weapon.gd:337-354).
    The spread grows with weapon count, de-synchronizing volleys. The mean equals
    basis EXCEPT when the low bound floors at 1 (basis - Δ < 1 — fast weapons at
    high weapon counts): there the mean skews above basis, so those weapons fire
    slightly slower than basis implies and nominal DPS modestly overstates them.
    The coach's cycle_time uses raw basis and does not model this skew (see
    docs/roadmap.md).
    """
    n = min(max(weapon_count, 1), 6)
    delta = min(n * cooldown_basis_frames / 5.0, n * 5.0)
    lo = max(1.0, cooldown_basis_frames - delta)
    # Clamp hi >= lo so the degenerate basis < 1 case (no base-game weapon has
    # a sub-1-frame cooldown) can't return an inverted range.
    return (lo, max(lo, cooldown_basis_frames + delta))


def cadence_profile(cycle_time: float, total_dps: float,
                    cooldown_basis_frames: float, weapon_count: int = 1,
                    *, burst_reload: bool = False) -> dict:
    """Per-weapon cadence descriptors decomposing DPS into rate x burst, plus
    the verified dead-window gap range. See docs/cadence-mechanics.md.

    Invariant: damage_per_attack * attacks_per_second == total_dps.
    The gap range derives from cooldown_jitter; the recoil portion of the
    cycle is common to both bounds and cancels, so no separate recoil value
    is needed. Caller must ensure cycle_time > 0.
    """
    aps = 1.0 / cycle_time
    lo_f, hi_f = cooldown_jitter(cooldown_basis_frames, weapon_count)
    # gap_range_s builds on cycle_time, which for burst-reload weapons already
    # amortizes the long reload — so their range is average-based, not the felt
    # fast-then-reload rhythm (flagged via burst_reload; see docs/cadence-mechanics.md).
    recoil_term = cycle_time - cooldown_basis_frames / 60.0
    if aps >= 3.0:
        label = "sustained"
    elif aps >= 1.0:
        label = "moderate"
    else:
        label = "bursty"
    return {
        "attacks_per_second": aps,
        "seconds_between_attacks": cycle_time,
        "damage_per_attack": total_dps * cycle_time,
        "cadence": label,
        "gap_range_s": [recoil_term + lo_f / 60.0, recoil_term + hi_f / 60.0],
        "burst_reload": burst_reload,
    }


# --- Stat-aware game-exact engine -------------------------------------------
# Evidence: recovered/singletons/weapon_service.gd (init pipeline),
# recovered/weapons/shooting_behaviors/*.gd (timing), recovered/entities/
# units/unit/unit.gd:285-301 (crit roll). See docs/dps-engine.md.

GD_MIN_COOLDOWN = 2.0  # frames; weapon_service.gd:5


def game_round(x: float) -> int:
    """GDScript round(): half away from zero (round(32.5) == 33)."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)  # type: ignore[return-value]


def game_int(x: float) -> int:
    """GDScript `as int`: truncation toward zero."""
    return math.trunc(x)  # type: ignore[return-value]


def effective_cooldown(cooldown: float, attack_speed_frac: float) -> int:
    """Attack-speed-adjusted cooldown in frames, exactly as the game computes it.

    weapon_service.gd:227-229 floors the base cooldown at MIN_COOLDOWN first,
    then :570-573 divides by (1+AS) for positive AS or multiplies by (1+|AS|)
    for negative AS, floors at MIN_COOLDOWN again, and truncates to int.
    `attack_speed_frac` is (stat_attack_speed + attack_speed_mod)/100.
    """
    cd = max(cooldown, GD_MIN_COOLDOWN)
    if attack_speed_frac > 0:
        return game_int(max(GD_MIN_COOLDOWN, cd / (1 + attack_speed_frac)))
    if attack_speed_frac < 0:
        return game_int(max(GD_MIN_COOLDOWN, cd * (1 + abs(attack_speed_frac))))
    return game_int(cd)


DEFAULT_ENGAGEMENT_DISTANCE = 70.0  # units; melee assumption constant (see spec)
MELEE_BASE_ATK_DURATION = 0.2      # melee_shooting_data.gd:4


def stat_aware_cycle_time(*, weapon_type: str, recoil_duration: float,
                          cooldown: float, attack_speed_frac: float,
                          max_range: float = 0.0,
                          engagement_distance: float | None = None,
                          burst: tuple[int, float] | None = None) -> float:
    """Seconds per attack cycle at a given attack speed, game-exact.

    The engine ticks cooldown only while not mid-swing (weapon.gd:193), so
    cycle = shooting_total_duration + effective_cooldown/60.
    Ranged shooting = 2*recoil_duration' (ranged_shooting_data.gd:10-15).
    Melee shooting = atk_duration/2 + back_duration + recoil_duration'
    (melee_shooting_data.gd:31-32) where atk/back have their own AS terms and
    atk_duration grows with distance-to-target (range_factor). The default
    engagement distance min(max_range, 70) is an assumption constant — enemies
    close in, and a weapon is never credited beyond its own reach.
    Positive AS divides recoil_duration (weapon_service.gd:230-232); negative
    AS does NOT lengthen it. Burst reload (Revolver/Chain Gun): every
    `every`-th cooldown draw is cd*multiplier INSTEAD of cd (weapon.gd:337-339),
    so the amortized cooldown is cd*((every-1)+multiplier)/every.
    """
    asf = attack_speed_frac
    recoil = recoil_duration / (1 + asf) if asf > 0 else recoil_duration
    cd = float(effective_cooldown(cooldown, asf))
    if burst is not None:
        every_x_shots, multiplier = burst
        cd = cd * ((every_x_shots - 1) + multiplier) / every_x_shots

    if weapon_type == "melee":
        dist = min(max_range, DEFAULT_ENGAGEMENT_DISTANCE) \
            if engagement_distance is None else engagement_distance
        # melee_shooting_data.gd:23-28
        range_factor = max(0.0, dist / min(max(70.0 * (1 + asf / 3), 70.0), 120.0))
        atk_duration = max(0.01, MELEE_BASE_ATK_DURATION - asf / 10) + range_factor * 0.15
        back_duration = MELEE_BASE_ATK_DURATION / (1 + 3 * asf) if asf > 0 \
            else MELEE_BASE_ATK_DURATION
        shooting = atk_duration / 2 + back_duration + recoil
    else:
        shooting = 2 * recoil

    return shooting + cd / 60


# Scaling-stat names are the full stat_* identifiers from the .tres; the
# coach's stat blocks use short names (Stats schema). One irregular case:
# the game's stat_percent_damage displays as "% Damage" and the schema calls
# it `damage`.
_SHORT_BY_STAT_NAME = {"stat_percent_damage": "damage"}


def stat_value(stats: dict, stat_name: str, level: float = 0.0) -> float:
    """Player-stat value for a full `stat_*` scaling name (0.0 if absent).

    `stat_levels` scales with player level, not a stat
    (weapon_service.gd:473-474).
    """
    if stat_name == "stat_levels":
        return float(level)
    short = _SHORT_BY_STAT_NAME.get(stat_name, stat_name.removeprefix("stat_"))
    return float(stats.get(short, 0.0))


def per_hit_damage(base_damage: float, scaling_stats: list, stats: dict, *,
                   level: float = 0.0, set_bonus_pct: float = 0.0) -> int:
    """One landed hit's damage before crit, game-exact.

    Step A (weapon_service.gd:489,469): d1 = max(1, base + Σ stat_i*coef_i)
    truncated to int. Step B (:239-249): d2 = max(1, round(d1 * (set_bonus
    + 1 + %damage/100))) — GDScript round, half away from zero.
    `set_bonus_pct` is the weapon-class-bonus percent bucket; the coach passes
    0 (character class bonuses are advisory — see spec decision 7).
    """
    total = sum(stat_value(stats, entry[0], level) * float(entry[1])
                for entry in scaling_stats or [])
    d1 = game_int(max(1.0, base_damage + total))
    bracket = set_bonus_pct / 100 + 1 + stat_value(stats, "stat_percent_damage") / 100
    return game_int(max(1, game_round(d1 * bracket)))


def expected_hit_damage(per_hit: int, weapon_crit_chance: float,
                        crit_damage: float, player_crit_chance: float = 0.0) -> float:
    """Expected damage of one landed hit, folding crit as an expectation.

    Total crit chance = weapon base + player stat/100 (weapon_service.gd:253),
    clamped to [0, 1] (cap defaults to LARGE_NUMBER, player_run_data.gd:436 —
    effectively uncapped, but a chance saturates at certainty). A crit deals
    round(damage * crit_damage) (unit.gd:299-300).
    """
    cc = min(1.0, max(0.0, weapon_crit_chance + player_crit_chance / 100))
    return (1 - cc) * per_hit + cc * game_round(per_hit * crit_damage)


def weapon_dps_profile(rec: dict, stats: dict, *, level: float = 0.0,
                       aoe_enemies_hit: float = 1.0,
                       engagement_distance: float | None = None) -> dict:
    """Realized expected DPS of one weapon record at a full stat block.

    Direct line: expected_hit_damage * accuracy / cycle_time. Proc lines from
    `proc_effects` re-run the same pipeline (weapon_damage re-deals the
    weapon's own hit; burn ticks run scaling+%damage without crit; companion
    projectiles carry their own damage/scaling/crit). `aoe_enemies_hit`
    multiplies proc enemies-hit assumptions, as before.

    Companion damage pipeline verified against
    recovered/effects/weapons/projectiles_on_hit_effect.gd (calls
    WeaponService.init_ranged_stats(weapon_stats, player_index, is_special_spawn=true))
    and recovered/singletons/weapon_service.gd:init_base_stats: damage scaling
    (:237) and %damage bonus (:239,249) apply unconditionally, and player crit
    chance is added (:252-253, gated only on `not is_structure` — companions are
    not structures) — the full pipeline the brief assumed, so no fallback needed.
    """
    asf = (stat_value(stats, "stat_attack_speed")
           + float(rec.get("attack_speed_mod", 0.0))) / 100
    burst = None
    every = rec.get("additional_cooldown_every_x_shots", -1)
    mult = rec.get("additional_cooldown_multiplier", -1.0)
    if isinstance(every, int) and every > 0 and mult and mult > 0:
        burst = (every, float(mult))
    is_melee = rec.get("weapon_type") == "melee"
    dist_used = (min(float(rec.get("max_range", 0.0)), DEFAULT_ENGAGEMENT_DISTANCE)
                 if engagement_distance is None else engagement_distance) if is_melee else None
    ct = stat_aware_cycle_time(
        weapon_type=rec.get("weapon_type", "ranged"),
        recoil_duration=float(rec.get("recoil_duration", 0.0)),
        cooldown=float(rec.get("cooldown", 0.0)),
        attack_speed_frac=asf,
        max_range=float(rec.get("max_range", 0.0)),
        engagement_distance=dist_used if is_melee else None,
        burst=burst)

    hit = per_hit_damage(float(rec["base_damage"]), rec.get("scaling_stats") or [],
                         stats, level=level)
    cc_total = min(1.0, max(0.0, float(rec.get("crit_chance", 0.0))
                            + stat_value(stats, "stat_crit_chance") / 100))
    expected = expected_hit_damage(hit, float(rec.get("crit_chance", 0.0)),
                                   float(rec.get("crit_damage", 0.0)),
                                   stat_value(stats, "stat_crit_chance"))
    accuracy = float(rec.get("accuracy", 1.0))
    base_dps = expected * accuracy / ct if ct > 0 else 0.0

    proc_dps = 0.0
    for eff in rec.get("proc_effects") or []:
        kind = eff.get("kind")
        if kind == "weapon_damage":
            proc_dps += (base_dps * float(eff["chance"])
                         * float(eff["enemies_hit"]) * aoe_enemies_hit
                         * float(eff.get("multiplier", 1.0)))
        elif kind == "burn_dot":
            tick = per_hit_damage(float(eff["damage"]),
                                  eff.get("scaling_stats") or [], stats, level=level)
            proc_dps += tick / float(eff["tick_interval"])
        elif kind == "companion":
            c_hit = per_hit_damage(float(eff["damage"]),
                                   eff.get("scaling_stats") or [], stats, level=level)
            c_expected = expected_hit_damage(
                c_hit, float(eff.get("crit_chance", 0.0)),
                float(eff.get("crit_damage", 0.0)),
                stat_value(stats, "stat_crit_chance"))
            proc_dps += (c_expected * float(eff["count"])
                         * float(eff["enemies_hit"]) * aoe_enemies_hit
                         / ct * accuracy) if ct > 0 else 0.0

    return {
        "dps": base_dps + proc_dps,
        "base_dps": base_dps,
        "proc_dps": proc_dps,
        "cycle_time": ct,
        "per_hit_damage": hit,
        "expected_hit_damage": expected,
        "crit_chance_total": cc_total,
        "effective_cooldown_frames": effective_cooldown(
            float(rec.get("cooldown", 0.0)), asf),
        "engagement_distance_used": dist_used,
    }
