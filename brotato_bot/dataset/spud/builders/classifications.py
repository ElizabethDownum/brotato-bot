# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Mechanism-based classification of non-DPS weapon effects.

An effect that has no PROC_MODELS damage model may still be a fully
understood mechanic — a passive stat grant, an economy perk, crowd control, a
crit-gated delivery modifier, or a special (execute / per-copy stack /
structure spawner). classify_effect() recognizes these by MECHANISM — the
attached script's basename, the Effect base class's storage_method, and
finally the key string — never by weapon name, because identical key strings
hide different mechanics (stat_percent_damage is a flat debuff nowhere and a
stand-still-gated one on Jousting Lance). Classified effects land in the
weapon record's `classified_effects` (with citation-ready metadata) instead
of `unmodeled_effects`, which then means strictly "uninvestigated."

Categories and the evidence behind each classification are documented in
docs/proc-mechanics.md ("Effect classification") and the research dossiers
under docs/superpowers/research/. Every script name below was verified to be
the engine's actual dispatch target (or a no-op NullEffect whose key string
is consumed elsewhere) — see the dossiers.
"""

from __future__ import annotations

CATEGORIES = frozenset({
    "stat_rider",        # flat player-stat grant while held (SUM storage)
    "dynamic",           # state/build/time-dependent — no honest static number
    "economy",           # gold/xp event effects
    "cc",                # slows/crowd control, zero damage
    "delivery_modifier", # crit-gated pierce/bounce on the weapon's own line
    "drawback",          # self-damage cost
    "execute",           # chance to force hit damage = target's current HP
    "stack",             # per-extra-copy flat weapon-stat bonus
    "structure",         # spawns a persistent structure (mines, garden)
})

# Scripts whose class IS the mechanic (engine dispatches on script class, or
# the .tres ships key="" so the script is the only identity).
_DYNAMIC_SCRIPTS = frozenset({
    "gain_stat_for_every_stat_effect.gd",        # missing-HP-scaled grant (Sharp Tooth)
    "temp_stats_per_interval_effect.gd",         # unbounded interval accumulator (Drill T4)
    "gain_stat_every_killed_enemies_effect.gd",  # per-weapon kill ratchet (Ghost weapons)
    "player_no_hit_effect.gd",                   # no-hit damage ramp (Rail Gun)
})
_CC_SCRIPTS = frozenset({
    "weapon_slow_on_hit_effect.gd",  # engineering-scaled percent slow (Particle Accelerator)
    "slow_in_zone_effect.gd",        # inert marker; slow is hardcoded in taser_projectile.gd
})

# Flat-SUM keys that are player-stat grants but don't start with "stat_".
_EXTRA_RIDER_KEYS = frozenset({"xp_gain", "knockback", "consumable_heal",
                               "burning_spread"})


def classify_effect(eff: dict) -> dict | None:
    """Classify a modeled-less effect record, or return None (→ unmodeled)."""
    key = str(eff.get("key", "") or "")
    script = str(eff.get("script", "") or "")

    if script == "one_shot_on_hit_effect.gd":
        return {"key": key or "one_shot_on_hit", "category": "execute",
                "execute_chance_per_hit": float(eff.get("value", 0)) / 100.0}
    if script == "weapon_stack_effect.gd":
        return {"key": key or "weapon_stack", "category": "stack",
                "stat_name": eff.get("stat_name"),
                "bonus_per_extra_copy": eff.get("value")}
    if script in ("structure_effect.gd", "turret_effect.gd"):
        stats = eff.get("stats") or {}
        spawn_cooldown = eff.get("spawn_cooldown")
        if not isinstance(spawn_cooldown, (int, float)) or spawn_cooldown < 0:
            # Spawning turrets (e.g. Pruner's garden) leave the inherited
            # spawn_cooldown field at its -1 sentinel; their real cadence is
            # the structure's own stats.cooldown, in frames.
            spawn_cooldown = stats.get("cooldown")
        return {"key": key or "structure", "category": "structure",
                # Raw engine value: seconds for StructureEffect's own field,
                # frames when falling back to a turret's stats.cooldown —
                # units documented in docs/proc-mechanics.md.
                "spawn_cooldown": spawn_cooldown,
                "structure_damage": stats.get("damage"),
                "structure_scaling_stats": stats.get("scaling_stats")}
    if script in _DYNAMIC_SCRIPTS:
        return {"key": key, "category": "dynamic"}
    if script in _CC_SCRIPTS:
        return {"key": key, "category": "cc"}

    if key in ("pierce_on_crit", "bounce_on_crit"):
        return {"key": key, "category": "delivery_modifier",
                "on_crit_extra_hits_max": eff.get("value")}
    if key == "gold_on_crit_kill":
        return {"key": key, "category": "economy",
                "gold_chance_on_crit_kill": float(eff.get("value", 0)) / 100.0}
    if key == "lose_hp_per_second":
        return {"key": key, "category": "drawback",
                "self_damage_per_second": eff.get("value")}

    # KEY_VALUE storage (effect.gd:62-83) routes the value into a named
    # conditional bucket (temp_stats_while_not_moving / temp_stats_on_hit /
    # additional_weapon_effects) — state-dependent, no static number.
    if key and eff.get("storage_method", 0) == 1:
        return {"key": key, "category": "dynamic"}
    if key.startswith("stat_") or key in _EXTRA_RIDER_KEYS:
        return {"key": key, "category": "stat_rider", "value": eff.get("value")}
    return None
