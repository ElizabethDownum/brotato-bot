# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

import re

from brotato_bot.dataset.spud.builders.localization import resolve_text
from brotato_bot.dataset.spud.scene import parse_scene_node
from brotato_bot.dataset.spud.tres import parse_tres

# Attack-behavior script basename -> (attack kind, ability tag or None).
_BEHAVIOR_KIND = {
    "shooting_attack_behavior": ("ranged", None),
    "charging_attack_behavior": ("charging", "charger"),
    "spawning_attack_behavior": ("ranged", "spawner"),
}

_BOSS_ROOT_RE = re.compile(r'^\[node name="Boss" instance=', re.MULTILINE)


def _num(d: dict, key: str, default: float = 0.0):
    v = d.get(key)
    return v if isinstance(v, (int, float)) else default


def _classify_attack(scene_text: str | None) -> tuple[str, list[str], dict]:
    """Return (kind, abilities, attack_params) from an enemy scene.

    kind derives from the primary AttackBehavior node's own script (the enemy's
    main attack); auxiliary/state behavior nodes are intentionally ignored
    (only the primary AttackBehavior node's script is read).
    Boss scenes (root node "Boss") carry a bespoke_kit_not_modeled ability.
    No AttackBehavior node -> pure contact melee. Numeric params come from the
    AttackBehavior node only for ranged attacks.
    """
    if not scene_text:
        return "melee", [], {}
    doc = parse_tres(scene_text)
    abilities: list[str] = []
    if _BOSS_ROOT_RE.search(scene_text):
        abilities.append("bespoke_kit_not_modeled")

    node = parse_scene_node(scene_text, "AttackBehavior")
    kind = "melee"
    ref = node.get("script")
    if isinstance(ref, dict) and "__ext__" in ref:
        path = str((doc.ext_resources.get(ref["__ext__"]) or {}).get("path", ""))
        base = path.rsplit("/", 1)[-1]
        if base.endswith("_attack_behavior.gd"):
            slug = base[: -len(".gd")]
            k, ability = _BEHAVIOR_KIND.get(slug, ("melee", None))
            kind = k
            if ability and ability not in abilities:
                abilities.append(ability)

    params: dict = {}
    if kind == "ranged":
        params = {
            "projectile_damage": _num(node, "damage"),
            "projectile_dmg_per_wave": _num(node, "damage_increase_each_wave"),
            "number_projectiles": int(_num(node, "number_projectiles", 1)),
        }
    return kind, abilities, params


def build_enemy_record(stats_text: str, scene_text: str | None, *, enemy_id: str,
                       name: str, tr: dict[str, str] | None = None) -> dict:
    s = parse_tres(stats_text).resource
    kind, abilities, attack_params = _classify_attack(scene_text)
    return {
        "id": enemy_id,
        "name": name,
        "display_name": resolve_text(tr, None, name),
        "base": {
            "health": _num(s, "health"),
            "speed": _num(s, "speed"),
            "speed_randomization": _num(s, "speed_randomization"),
            "damage": _num(s, "damage"),
            "armor": _num(s, "armor"),
            "attack_cd": _num(s, "attack_cd"),
            "knockback_resistance": _num(s, "knockback_resistance"),
        },
        "per_wave": {
            "health": _num(s, "health_increase_each_wave"),
            "damage": _num(s, "damage_increase_each_wave"),
            "armor": _num(s, "armor_increase_each_wave"),
        },
        "attack": {"kind": kind, **attack_params},
        "abilities": abilities,
    }
