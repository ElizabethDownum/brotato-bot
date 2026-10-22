# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Typed argument models for the MCP tool surface.

These exist so the tool schema tells the model exactly which keys a stats object
accepts, instead of shipping a bare `dict` (any keys) that the model has to guess
at — a wrong or misspelled key would otherwise be silently read as zero.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Stats(BaseModel):
    """A player's current run stats, keyed by Brotato stat name in SHORT form
    (no `stat_` prefix), e.g. `ranged_damage`, `melee_damage`, `engineering`.

    Every field is optional; omit a stat to treat it as its base/zero value.
    The named fields below are the standard Brotato stats so the model knows the
    exact keys, but extra keys are still accepted (extra="allow") so a valid stat
    is never rejected. Values are raw stat totals (e.g. ranged_damage=45).
    """

    model_config = ConfigDict(extra="allow")

    max_hp: float | None = None
    hp_regeneration: float | None = None
    lifesteal: float | None = None
    damage: float | None = None
    melee_damage: float | None = None
    ranged_damage: float | None = None
    elemental_damage: float | None = None
    attack_speed: float | None = None
    crit_chance: float | None = None
    engineering: float | None = None
    range: float | None = None
    armor: float | None = None
    dodge: float | None = None
    speed: float | None = None
    luck: float | None = None
    harvesting: float | None = None
    curse: float | None = None  # Abyssal Terrors DLC; some DLC weapons scale with it
    level: float | None = None  # player level, for stat_levels-scaling weapons

    def as_dict(self) -> dict:
        """Plain dict of the stats actually provided (None fields dropped),
        including any extra keys, for the pure answer/evaluate functions."""
        return self.model_dump(exclude_none=True)
