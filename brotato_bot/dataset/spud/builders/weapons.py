# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

from brotato_bot.dataset.spud import calc
from brotato_bot.dataset.spud.builders.classifications import classify_effect
from brotato_bot.dataset.spud.builders.localization import resolve_text
from brotato_bot.dataset.spud.builders.procs import PROC_MODELS
from brotato_bot.dataset.spud.schemas import Stats
from brotato_bot.dataset.spud.tres import parse_tres, TresDoc


def _weapon_type(doc: TresDoc) -> str:
    """"melee"/"ranged" from the stats script ext_resource basename.

    The stats .tres attaches its type-defining script
    (weapons/weapon_stats/{melee,ranged}_weapon_stats.gd) as an ext_resource
    referenced by `script = ExtResource(N)`. Fixtures/records with no such
    ext_resource (most unit-test fixtures, which don't exercise weapon-type
    behavior) default to "ranged" rather than raising.
    """
    for ext in doc.ext_resources.values():
        path = str(ext.get("path") or "")
        if path.endswith("weapon_stats.gd"):
            return "melee" if "melee_weapon_stats" in path else "ranged"
    return "ranged"


def _check_scaling_stat(name: str, weapon_id: str) -> None:
    """Guard against a scaling-stat name the stat-aware engine can't map.

    Mirrors calc.stat_value's own resolution rules exactly (stat_levels,
    calc._SHORT_BY_STAT_NAME's irregular short names, or a stat_* name whose
    removeprefix("stat_") is a real Stats field) so a build fails loudly
    instead of the engine silently reading 0.0 for an unmapped stat at
    query time.
    """
    if name == "stat_levels" or name in calc._SHORT_BY_STAT_NAME:
        return
    if name.removeprefix("stat_") in Stats.model_fields:
        return
    raise ValueError(f"unknown scaling stat {name!r} on {weapon_id}")


def _validate_scaling_stats(scaling_stats: list, weapon_id: str) -> None:
    for entry in scaling_stats or []:
        if isinstance(entry, list) and entry:
            _check_scaling_stat(str(entry[0]), weapon_id)


def _weapon_effect_record(text: str, companion_texts: dict[str, str] | None = None) -> dict:
    """A weapon's on-hit effect as plain scalar fields.

    Drops nested resource references (script, explosion_scene, …) and keeps the
    gameplay scalars — e.g. the Shredder's `key="effect_explode_custom"` with
    `chance=0.5`. The script ext_resource's basename is kept as `script`, since
    the engine dispatches many effects on script class (and blank-key effects
    have nothing else identifying them). Some effects keep their real numbers
    on companion resources instead of inline (burning_data / weapon_stats /
    stats); each given companion's scalar fields nest under its own field name
    rather than flattening, since the files carry unrelated same-named
    boilerplate (e.g. `value`).
    """
    doc = parse_tres(text)
    r = doc.resource
    record = {k: v for k, v in r.items()
              if not (isinstance(v, dict) and ("__ext__" in v or "__sub__" in v))}
    script_ref = r.get("script")
    if isinstance(script_ref, dict) and "__ext__" in script_ref:
        ext = doc.ext_resources.get(script_ref["__ext__"]) or {}
        script_path = str(ext.get("path", ""))
        if script_path:
            record["script"] = script_path.rsplit("/", 1)[-1]
    for field, extra_text in (companion_texts or {}).items():
        extra = parse_tres(extra_text).resource
        record[field] = {k: v for k, v in extra.items()
                        if not (isinstance(v, dict) and ("__ext__" in v or "__sub__" in v))}
    return record


def build_weapon_record(stats_text: str, data_text: str,
                        effect_texts: list[str] | None = None,
                        effect_companion_texts: list[dict[str, str] | None] | None = None, *,
                        weapon_id: str, name: str, tier: int,
                        classes: list[str] | None = None,
                        proc_models: dict | None = None,
                        tr: dict[str, str] | None = None) -> dict:
    stats_doc = parse_tres(stats_text)
    s = stats_doc.resource
    d = parse_tres(data_text).resource

    weapon_type = _weapon_type(stats_doc)
    cooldown = float(s.get("cooldown", 0))
    recoil_duration = float(s.get("recoil_duration", 0.0))
    base_damage = float(s.get("damage", 0))
    accuracy = float(s.get("accuracy", 1.0))
    max_range = float(s.get("max_range", 0.0))
    attack_speed_mod = float(s.get("attack_speed_mod", 0.0))
    scaling_stats = s.get("scaling_stats", []) or []
    _validate_scaling_stats(scaling_stats, weapon_id)

    every = s.get("additional_cooldown_every_x_shots", -1)
    mult = s.get("additional_cooldown_multiplier", -1.0)
    burst = None
    if isinstance(every, int) and every > 0 and isinstance(mult, (int, float)) and mult > 0:
        burst = (every, float(mult))

    companions = effect_companion_texts or [None] * len(effect_texts or [])
    effects = [_weapon_effect_record(t, c)
               for t, c in zip(effect_texts or [], companions, strict=True)]
    models = PROC_MODELS if proc_models is None else proc_models
    proc_effects: list[dict] = []
    unmodeled: list[str] = []
    classified: list[dict] = []
    for eff in effects:
        model = models.get(str(eff.get("key", "")))
        source = model["damage_source"] if model is not None else None
        if source == "weapon_damage":
            proc_effects.append({
                "kind": "weapon_damage",
                "chance": float(eff.get("chance", 1.0)),
                "enemies_hit": model["default_enemies_hit"],
                "multiplier": model["damage_multiplier"],
            })
        elif source == "burn_dot":
            bd = eff.get("burning_data") or {}
            chance = float(bd.get("chance", 0.0))
            damage = bd.get("damage")
            duration = float(bd.get("duration", 0))
            window = duration * model["tick_interval"]
            ct_zero_as = calc.stat_aware_cycle_time(
                weapon_type=weapon_type, recoil_duration=recoil_duration,
                cooldown=cooldown, attack_speed_frac=0.0, max_range=max_range,
                burst=burst)
            if chance == 1.0 and damage is not None and window > 0 and ct_zero_as <= window:
                bd_scaling = bd.get("scaling_stats") or []
                _validate_scaling_stats(bd_scaling, weapon_id)
                proc_effects.append({
                    "kind": "burn_dot",
                    "damage": float(damage),
                    "scaling_stats": bd_scaling,
                    "tick_interval": model["tick_interval"],
                })
            elif eff.get("key"):
                unmodeled.append(str(eff["key"]))
        elif source == "companion_ranged_stats":
            ws = eff.get("weapon_stats") or {}
            damage = ws.get("damage")
            count = float(eff.get("value", 0))
            bounce = int(ws.get("bounce", 0)) if bool(ws.get("can_bounce", True)) else 0
            ok = damage is not None and count > 0
            if bool(eff.get("auto_target_enemy", False)):
                # Targeted chain: assume the nominal chain fully connects.
                # No decaying-bounce math exists — lossy bounces fall back.
                ok = ok and (bounce == 0 or float(ws.get("bounce_dmg_reduction", 0.5)) == 0.0)
                enemies_hit = 1.0 + bounce
            else:
                # Untargeted spray: one expected hit per volley (documented
                # assumption, exploding default_enemies_hit precedent).
                ok = ok and bounce == 0
                enemies_hit = 1.0
            if ok:
                ws_scaling = ws.get("scaling_stats") or []
                _validate_scaling_stats(ws_scaling, weapon_id)
                proc_effects.append({
                    "kind": "companion",
                    "damage": float(damage),
                    "scaling_stats": ws_scaling,
                    "crit_chance": float(ws.get("crit_chance", 0.0)),
                    "crit_damage": float(ws.get("crit_damage", 0.0)),
                    "count": count,
                    "enemies_hit": enemies_hit,
                })
            elif eff.get("key"):
                unmodeled.append(str(eff["key"]))
        else:
            entry = classify_effect(eff)
            if entry is not None:
                classified.append(entry)
            elif eff.get("key") or eff.get("script"):
                # Blank-key effects were previously dropped silently; naming
                # them by script keeps hidden mechanics visible.
                unmodeled.append(str(eff.get("key") or eff["script"]))

    return {
        "id": weapon_id,
        "name": name,
        "display_name": resolve_text(tr, d.get("name"), name),
        "description": resolve_text(tr, d.get("description")),
        "tier": tier,
        "weapon_type": weapon_type,
        "base_damage": base_damage,
        "cooldown": cooldown,
        "recoil_duration": recoil_duration,
        "max_range": max_range,
        "attack_speed_mod": attack_speed_mod,
        "burst_reload": burst is not None,
        "additional_cooldown_every_x_shots": every,
        "additional_cooldown_multiplier": mult,
        "accuracy": accuracy,
        "crit_chance": float(s.get("crit_chance", 0.0)),
        "crit_damage": float(s.get("crit_damage", 0.0)),
        "piercing": s.get("piercing", 0),
        "nb_projectiles": s.get("nb_projectiles", 1),
        "scaling_stats": scaling_stats,
        "can_have_negative_knockback": bool(s.get("can_have_negative_knockback", False)),
        "base_knockback": s.get("knockback", 0),
        "sets": list(classes or []),
        # On-hit effects, resolved from the data .tres `effects`
        # ext_resources. Effects with a verified PROC_MODELS entry contribute
        # a proc_effects descriptor (evaluated at query time by
        # calc.weapon_dps_profile); classified non-DPS mechanics land in
        # classified_effects; anything left is listed in unmodeled_effects.
        "effects": effects,
        "proc_effects": proc_effects,
        "unmodeled_effects": unmodeled,
        "classified_effects": classified,
    }
