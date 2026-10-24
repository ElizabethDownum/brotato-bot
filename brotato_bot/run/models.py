"""Pydantic models for one collected bot run (built by ``collect.summarize``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Outcome = Literal["win", "death", "incomplete"]


class WaveRow(BaseModel):
    """One wave. ``completed`` is False for the wave the player died in (no ``wave_end``
    line is written for it); its ``damage_taken`` comes from the death line's ``dmg_w``."""

    wave: int
    hp_end: int | None = None
    gold_end: int | None = None
    damage_taken: int | None = None
    kills: int | None = None
    completed: bool = True
    stats: dict[str, float] = Field(default_factory=dict)


class OfferRow(BaseModel):
    wave: int | None = None
    view: int | None = None
    gold: int | None = None
    items: list[dict] = Field(default_factory=list)
    bought: list[str] = Field(default_factory=list)


class MaterialRow(BaseModel):
    wave: int
    floors: list[float] = Field(default_factory=list)
    bag: float | None = None


class ShopRow(BaseModel):
    """One shop action, from a ``shop`` event: ``action`` is buy/reroll/lock/pass/ban/go and
    ``source`` is rule/haiku."""

    wave: int | None = None
    action: str
    item: str | None = None
    price: int | None = None
    score: float | None = None
    source: str | None = None
    gold_after: int | None = None


class LevelupRow(BaseModel):
    wave: int | None = None
    id: str | None = None
    picked: str
    source: str
    alternatives: list[str] = Field(default_factory=list)
    score: float | None = None


class DecisionRow(BaseModel):
    wave: int | None = None
    id: str = ""
    kind: str
    action: str | None = None
    option_index: int | None = None
    rulings: list[dict[str, Any]] = Field(default_factory=list)
    rulings_missing: int | None = None
    source: str
    confidence: float | None = None
    rationale: str | None = None


class CheckpointRow(BaseModel):
    wave: int | None = None
    id: str = ""
    action: str | None = None
    applied: str
    reason: str = ""


class DeathRecord(BaseModel):
    wave: int
    killer: str = ""
    last_threats: list[str] = Field(default_factory=list)
    weapons: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    dmg_w: int | None = None
    position: Any = None


class RunSummary(BaseModel):
    run_id: str
    character_id: str = ""
    danger: int | None = None
    plan_id: str = ""
    profile_id: int | None = None
    start_wave: int = 1
    target_challenge: str | None = None
    outcome: Outcome
    end_outcome: str | None = None
    death_wave: int | None = None
    waves: list[WaveRow] = Field(default_factory=list)
    shop: list[ShopRow] = Field(default_factory=list)
    levelups: list[LevelupRow] = Field(default_factory=list)
    decisions: list[DecisionRow] = Field(default_factory=list)
    checkpoints: list[CheckpointRow] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    targets_completed: list[str] = Field(default_factory=list)
    death: DeathRecord | None = None
    notes: list[str] = Field(default_factory=list)
    target_waves: dict[str, int | None] = Field(default_factory=dict)
    offers: list[OfferRow] = Field(default_factory=list)
    crates: list[ShopRow] = Field(default_factory=list)
    build: dict[str, list[str]] | None = None
    materials: list[MaterialRow] = Field(default_factory=list)
    launch: dict | None = None
    goal_items: list[str] = Field(default_factory=list)

    @property
    def hp_end_last_wave(self) -> int | None:
        """HP at the end of the last completed wave (None before any wave ended)."""
        done = [w for w in self.waves if w.completed]
        return done[-1].hp_end if done else None
