# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Expected-damage models for weapon on-hit proc effects.

A model may only be added here with decompiled-code evidence from recovered/
(the builders/mechanics.py standard) — record the evidence in
docs/proc-mechanics.md. Effects without a model contribute zero DPS and are
listed in the weapon record's `unmodeled_effects`, so rankings stay honest
about what they ignore.

Model schema, keyed by effect `key` — dispatch is on damage_source:
    "weapon_damage" — the proc re-deals the weapon's own damage line
        (base + scaling). Fields: damage_multiplier (fraction of the
        weapon's line the proc deals), default_enemies_hit (assumed average
        enemies caught per proc — the softest number in the model; answers
        surface it as an assumption and let callers override it).
    "burn_dot" — damage-over-time proc; per-weapon numbers come from the
        effect's burning_data companion. Fields: tick_interval (engine
        constant, seconds).
    "companion_ranged_stats" — spawn-projectiles-on-hit; the proc's own
        damage line lives on the effect's weapon_stats companion. No model
        fields — per-weapon numbers come from the companion, and the
        enemies-hit policy lives in builders/weapons.py.
"""

from __future__ import annotations

# Exploding effect: a chance-per-hit to spawn an explosion that re-deals the
# weapon's own current damage line (base + scaling stats), unmodified.
# Evidence: docs/proc-mechanics.md (recovered/weapons/weapon.gd:419-436,
# _on_Hitbox_hit_something — `_explosion_args.damage = _hitbox.damage`).
# All three keys attach the same recovered/effects/weapons/exploding_effect.gd
# script and are dispatched on script class at runtime, so they share one
# model: Shredder T1-3 (effect_explode_custom), Fireball/Nuclear
# Launcher T3-4/Rocket Launcher/Shredder T4 (effect_explode), and
# Plank/Power Fist/Plasma Sledgehammer/Dextroyer (effect_explode_melee).
_EXPLODE_MODEL = {
    "damage_source": "weapon_damage",
    "damage_multiplier": 1.0,
    # The explosion's ignored_objects excludes the enemy that was just hit
    # (weapon.gd:435), so it can only damage OTHER enemies in the blast.
    # 1.0 assumes one other enemy is caught — conservative for crowds,
    # optimistic against a lone target (true value there is 0).
    "default_enemies_hit": 1.0,
}

# Burning effect: a chance-per-hit damage-over-time proc, independent of the
# weapon's own damage line (it scales off stat_elemental_damage, not RD).
# Evidence: docs/proc-mechanics.md (unit.tscn:52 BurningTimer wait_time=0.5;
# unit.gd apply_burning/burn-tick handler). Modeled only when the weapon's
# own cycle_time fits inside the burn's duration window at chance==1.0 —
# verified true for every shipped burn weapon (Torch, Fireball, Wand,
# Flamethrower, Particle Accelerator, Flaming Knuckles). builders/weapons.py
# enforces this precondition and falls back to unmodeled_effects otherwise,
# rather than guess at an unverified duty-cycle model for chance < 1.0 or a
# slower weapon — no shipped weapon exercises either case.
_BURN_MODEL = {
    "damage_source": "burn_dot",
    "tick_interval": 0.5,
}

# Companion-projectile procs (ProjectilesOnHitEffect): every landed host hit
# unconditionally spawns `value` projectiles (no chance roll — value is a
# count) whose damage/crit/scaling live on a companion RangedWeaponStats
# resource (`weapon_stats = ExtResource(N)` on the effect .tres). One script
# class serves four keys, so all four share this model (same pattern as the
# exploding trio). Evidence: docs/proc-mechanics.md "Companion-projectile
# procs" + research dossiers 2026-07-05-family-{lightning,projectiles-on-hit,
# slows-cc}.md. The enemies-hit policy and precondition gates live in
# builders/weapons.py: targeted chains (auto_target_enemy=true) count
# 1+bounce, gated on lossless bounce; untargeted sprays count 1.0 per volley,
# gated on bounce==0 — the 1.0 is an assumption constant per the exploding
# model's default_enemies_hit precedent (optimistic vs. a lone enemy, where
# the true value is 0 — the spawn excludes the enemy that triggered it).
_COMPANION_PROJECTILE_MODEL = {
    "damage_source": "companion_ranged_stats",
}

PROC_MODELS: dict[str, dict] = {
    "effect_explode_custom": _EXPLODE_MODEL,
    "effect_explode": _EXPLODE_MODEL,
    "effect_explode_melee": _EXPLODE_MODEL,
    "effect_burning": _BURN_MODEL,
    "effect_lightning_on_hit": _COMPANION_PROJECTILE_MODEL,
    "effect_projectiles_on_hit": _COMPANION_PROJECTILE_MODEL,
    "EFFECT_PROJECTILES_ON_HIT": _COMPANION_PROJECTILE_MODEL,
    "EFFECT_SLOW_PROJECTILES_ON_HIT": _COMPANION_PROJECTILE_MODEL,
}
