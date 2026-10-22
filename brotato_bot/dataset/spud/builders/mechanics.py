# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Verified stat mechanics, encoded from decompiled code (see docs/stat-mechanics.md).

Only stats whose behavior has been confirmed against the game code are listed.
This table is authoritative for what the coach claims about stat mechanics.
"""

from __future__ import annotations


def _m(cap=None, special=None, safe_below_zero=False, safe_at_zero=False,
       avoid_positive=False, never_dead_weight=False, summary=None) -> dict:
    return {
        "cap": cap, "special": special, "safe_below_zero": safe_below_zero,
        "safe_at_zero": safe_at_zero, "avoid_positive": avoid_positive,
        "never_dead_weight": never_dead_weight, "summary": summary,
    }


_WEAPON_SCALING = ("Weapon scaling stat: each weapon whose scaling_stats lists "
                   "it adds coefficient x stat to that weapon's damage per hit; "
                   "it does nothing for weapons without a matching entry — check "
                   "the weapon record's scaling_stats.")

STAT_MECHANICS: dict[str, dict] = {
    "stat_max_hp": _m(cap={"cap_key": "hp_cap"},
                      summary="Capped via hp_cap, but the default cap is "
                              "LARGE_NUMBER (99999999) — effectively infinite "
                              "until an item (Handcuffs) sets a real ceiling "
                              "and freezes it for the run."),
    "stat_speed": _m(cap={"cap_key": "speed_cap"},
                     summary="Capped via speed_cap, but the default cap is "
                             "LARGE_NUMBER (99999999) — effectively infinite "
                             "until Shackles sets a real ceiling and freezes "
                             "it (cap-at-current-value)."),
    "stat_dodge": _m(cap={"cap_key": "dodge_cap"},
                     summary="Capped via dodge_cap (utils.gd get_capped_stat); "
                             "unlike hp/speed/crit_chance, the default cap is "
                             "60, not effectively-infinite — it binds from the "
                             "start of every run."),
    "stat_crit_chance": _m(cap={"cap_key": "crit_chance_cap"},
                           summary="Capped via crit_chance_cap (utils.gd "
                                   "get_capped_stat), but the default cap is "
                                   "LARGE_NUMBER (99999999) — effectively "
                                   "infinite until an item sets a real "
                                   "ceiling. Regardless of that in-game cap, "
                                   "the DPS engine clamps the combined chance "
                                   "(weapon base + capped player stat/100) to "
                                   "[0, 1], since a probability can't exceed "
                                   "certainty (player_run_data.gd:436, "
                                   "weapon_service.gd:252-253). Crit is now "
                                   "folded into DPS as an expectation — "
                                   "(1-cc)*damage + cc*round(damage*"
                                   "crit_damage) — not a separate rolled "
                                   "burst line (see docs/dps-engine.md)."),
    "stat_curse": _m(cap={"cap_key": "curse_cap"}, special="curse_sqrt_penalty",
                     safe_below_zero=True, avoid_positive=True,
                     summary="Positive curse scales enemy damage/HP by a "
                             "sqrt(curse) factor (entity_service.gd) — avoid. "
                             "Negative curse is clamped to zero benefit: "
                             "harmless, but not a defensive gain."),
    "stat_hp_regeneration": _m(special="regen_zero_safe", safe_below_zero=True,
                               safe_at_zero=True,
                               summary="At or below 0 it is a harmless no-op — "
                                       "player.gd just stops the regen timer."),
    "stat_lifesteal": _m(special="lifesteal_negative_drains",
                         summary="Negative lifesteal actively drains HP on hit "
                                 "(unlike regen, which no-ops at or below 0)."),
    "stat_attack_speed": _m(special="attack_speed_universal", never_dead_weight=True,
                            summary="Universal cooldown multiplier, applied "
                                    "identically to ranged and melee weapons "
                                    "— never dead weight. Positive attack "
                                    "speed DIVIDES the cooldown by (1 + AS); "
                                    "negative attack speed MULTIPLIES the "
                                    "cooldown by (1 + |AS|) — both floored "
                                    "at the 2-frame minimum "
                                    "(weapon_service.gd:570-574, "
                                    "apply_attack_speed_mod_to_cooldown). "
                                    "Melee "
                                    "weapons ALSO get two extra "
                                    "attack-speed-sensitive swing terms "
                                    "ranged weapons don't have "
                                    "(melee_shooting_data.gd:17-28): the "
                                    "wind-up (atk_duration) shrinks linearly "
                                    "by attack_speed/10 (floored at 0.01s), "
                                    "and the back-swing (back_duration) "
                                    "divides by (1 + 3*attack_speed) for "
                                    "positive attack speed — a steeper, "
                                    "non-linear reduction than the wind-up "
                                    "term's flat subtraction — while "
                                    "negative attack speed leaves the "
                                    "back-swing at its flat 0.2s floor."),
    "knockback": _m(special="knockback_clamped_by_weapon_flag", safe_below_zero=True,
                    safe_at_zero=True,
                    summary="Clamped to non-negative per weapon unless the "
                            "weapon sets can_have_negative_knockback."),
    # Weapon scaling-damage stats — mechanism verified by this repo's own
    # hand-verified DPS model (docs/weapon-merge-dps-methodology.md).
    "stat_ranged_damage": _m(special="weapon_scaling_stat", summary=_WEAPON_SCALING),
    "stat_melee_damage": _m(special="weapon_scaling_stat", summary=_WEAPON_SCALING),
    "stat_elemental_damage": _m(special="weapon_scaling_stat", summary=_WEAPON_SCALING),
    "stat_engineering": _m(special="weapon_scaling_stat", summary=_WEAPON_SCALING),
    "stat_percent_damage": _m(
        summary="Multiplicative global weapon-damage bonus: damage x "
                "(1 + stat/100), combined with set-bonus and explosion-damage "
                "bonuses inside the same bracket before rounding "
                "(weapon_service.gd:239,249). Floor 1 damage. Not in "
                "utils.gd's cap list — uncapped. Negative values reduce all "
                "weapon damage."),
    "stat_armor": _m(
        summary="Damage-taken multiplier 10/(10 + abs(armor)/1.5) — "
                "diminishing returns, never reaches 0 (damage floor 1). Not "
                "in utils.gd's cap list — uncapped. NEGATIVE armor amplifies "
                "damage taken to (2 - coef) instead of reducing it "
                "(run_data.gd get_armor_coef, applied player.gd:310-311)."),
    "stat_luck": _m(
        summary="Drop-chance multiplier x (1 + luck/100). Not in utils.gd's "
                "cap list — uncapped. NEGATIVE luck DIVIDES chance by "
                "(1 + abs(luck)/100) rather than subtracting — a "
                "diminishing-returns penalty, not symmetric with the "
                "positive bonus (item_service.gd:161-165, 523-537)."),
    "stat_harvesting": _m(
        summary="Pays out at end of every wave: val = harvesting_stat + "
                "bonuses; if val >= 0 it grants BOTH gold AND xp equal to "
                "val (1 material + 1 XP per point) — if val < 0 it instead "
                "REMOVES that much gold every wave, it is not a no-op "
                "(main.gd manage_harvesting, 1289-1325). The stat itself "
                "grows ~5%/wave (ceil(stat * harvesting_growth/100), default "
                "growth 5) while stat > 0 and the run is within its normal "
                "waves; in endless it instead decays 20%/wave "
                "(ENDLESS_HARVESTING_DECREASE = 20); at stat <= 0 neither "
                "growth nor decay happens (main.gd "
                "_on_HarvestingTimer_timeout, 1521-1549). Not in utils.gd's "
                "cap list — uncapped."),
    "stat_range": _m(
        summary="Added flat to weapon max_range. Ranged weapons get the "
                "full stat (weapon_service.gd::init_ranged_stats:42 / "
                "init_ranged_pet_stats:78); melee weapons get only half "
                "(stat/2, weapon_service.gd::init_melee_stats:29 / "
                "init_melee_pet_stats:66) — both are floored at that "
                "weapon's own min_range, so it can shrink an increase's "
                "effect but never push range below the weapon's floor. Not "
                "in utils.gd's cap list — uncapped. Weapons flagged "
                "increase_projectile_speed_with_range (only Flamethrower "
                "T2-T4 ship with this) also scale projectile_speed = "
                "clamp(projectile_speed + projectile_speed/300 * "
                "stat_range, 50, 6000) "
                "(weapon_service.gd::_set_common_ranged_stats:115)."),
}
