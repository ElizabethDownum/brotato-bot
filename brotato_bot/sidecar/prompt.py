"""Prompt assembly for the sidecar's decision call.

``system_prompt(kind)`` is ``prompts/decide.md`` (``prompts/checkpoint.md`` for a
checkpoint) with ``decision.schema.json`` inlined. ``build(...)`` is the user message,
with these sections in order: Objective, State, Options, Plan, Relevant knowledge, Past
decisions, Answer format.

Inputs as the mod and the harness write them:

- ``request``: the mod's ``requests/<id>.json`` (``core/decision_client.gd``
  ``build_request``): ``{id, kind, screen, run_id, seq, state_path, options,
  deadline_ms}``. Shop options are ``{index, id, kind, price, score}``
  (``base_shop.gd`` ``_decision_options``), level-up options ``{index, id, stat, value,
  score}`` (``upgrades_ui.gd``); a checkpoint has none. A response's ``option_index``
  is ``options[i].index``, never the state file's ``shop[].index`` (a shop slot).
- ``state``: the state file, ``schema_version`` 1 (``core/state_export.gd``).
- ``plan``: ``plan.json`` (``{plan_id, character_id, target_challenge, plan}``).
- ``dataset``: ``data/brotato.json``. Weapon records are per family id with tiers 1-4
  (``weapon_smg`` tier 1 is the game's ``weapon_smg_1``); items, characters and sets are
  keyed by the game's ``my_id``.
- ``unlock_state``: ``unlocks.unlock_state(...)`` (``data/unlock_state.json``), optionally
  with a ``challenges`` key holding ``unlocks.challenge_texts(graph, dataset)`` for English
  challenge text; without it the objective falls back to the id and its progress entry.
- ``knowledge``: ``knowledge.cache.load_all`` (``{slug: text with front matter}``).
- ``experience``: ``experience.query`` rows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from brotato_bot.dataset.unlocks import challenge_texts
from brotato_bot.knowledge.cache import excerpt
from brotato_bot.sidecar.schema import SCHEMA_PATH

PROMPTS_DIR = Path(__file__).with_name("prompts")
SCHEMA_PLACEHOLDER = "{{DECISION_SCHEMA}}"
NO_TARGET = "no unlock target: optimise this character's run"
KNOWLEDGE_MAX_CHARS = 6000
PLAN_MAX_CHARS = 4000
PLAN_TRUNCATED = "... [plan truncated: {n} more chars]"
RECENT_SHOWN = 3
_WEAPON_TIER_ID = re.compile(r"^(weapon_.+)_(\d+)$")
_SLUG_JUNK = re.compile(r"[^a-z0-9]+")
# Record keys left out of the Options section: provenance, and text the dataset leaves empty.
_DROP_KEYS = frozenset({"source", "name"})

__all__ = ["SCHEMA_PATH", "build", "challenge_texts", "system_prompt"]


def system_prompt(kind: str) -> str:
    """The system prompt for a request ``kind``, with the decision schema inlined."""
    name = "checkpoint.md" if kind == "checkpoint" else "decide.md"
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8").strip()
    return text.replace(SCHEMA_PLACEHOLDER, schema_text)


# --- Dataset lookup -------------------------------------------------------------


class _Lookup:
    def __init__(self, dataset: dict) -> None:
        self.items = {r.get("id"): r for r in dataset.get("items") or [] if isinstance(r, dict)}
        self.weapons: dict[tuple[str, int], dict] = {}
        for r in dataset.get("weapons") or []:
            if isinstance(r, dict):
                self.weapons.setdefault((r.get("id"), r.get("tier")), r)
        self.characters = {
            r.get("id"): r for r in dataset.get("characters") or [] if isinstance(r, dict)
        }
        self.sets: dict[str, dict] = {}
        for r in dataset.get("sets") or []:
            if isinstance(r, dict):
                for key in (r.get("id"), r.get("name"), r.get("display_name")):
                    if key:
                        self.sets.setdefault(str(key), r)

    def record(self, item_id: str) -> dict | None:
        """The dataset record for a game ``my_id`` (item, or weapon ``<family>_<tier>``)."""
        if item_id in self.items:
            return self.items[item_id]
        m = _WEAPON_TIER_ID.match(item_id)
        if m:
            return self.weapons.get((m.group(1), int(m.group(2))))
        return None


def _display(rec: dict | None, fallback: str) -> str:
    if not rec:
        return fallback
    return str(rec.get("display_name") or rec.get("name") or fallback)


def _compact(rec: dict) -> str:
    kept = {k: v for k, v in rec.items() if k not in _DROP_KEYS and v not in ("", None, [], {})}
    return json.dumps(kept, ensure_ascii=False)


def _num(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _signed(v: Any) -> str:
    s = _num(v)
    return s if s.startswith("-") else "+" + s


def _set_lines(rec: dict, look: _Lookup) -> list[str]:
    lines = []
    for name in rec.get("sets") or []:
        s = look.sets.get(str(name))
        if not s:
            continue
        bonuses = "; ".join(
            f"{b.get('count')}: {(b.get('effect') or {}).get('key')} "
            f"{_signed((b.get('effect') or {}).get('value'))}"
            for b in s.get("bonuses") or []
            if isinstance(b, dict)
        )
        lines.append(f"  set {_display(s, str(name))}: {bonuses or 'no bonuses listed'}")
    return lines


# --- Sections -------------------------------------------------------------------


def _target(state: dict, plan: dict) -> str:
    for src in (state, plan):
        t = src.get("target_challenge") if isinstance(src, dict) else None
        if isinstance(t, str) and t:
            return t
    return ""


def _objective(state: dict, plan: dict, unlock_state: dict) -> list[str]:
    target = _target(state, plan)
    if not target:
        return [NO_TARGET + "."]
    texts = (unlock_state.get("challenges") or {}).get(target) or {}
    progress = (unlock_state.get("progress") or {}).get(target) or {}
    if texts.get("description"):
        name = texts.get("name")
        head = f"Target challenge: {target}" + (f" ({name})" if name else "")
        line = f"{head}: {texts['description']}."
    else:
        line = f"Target challenge: {target} (no English description available)."
        if progress.get("value") is not None:
            stat = progress.get("stat") or "-"
            line += f" Completion value {progress['value']}, stat {stat}."
    lines = [line]
    if progress.get("requires_character"):
        lines.append(f"It progresses only while playing {progress['requires_character']}.")
    for status in ("done", "open", "blocked"):
        if target in (unlock_state.get(status) or []):
            lines.append(f"Profile status: {status}.")
            break
    lines.append("Play this run to complete the target; survive while doing so.")
    return lines


def _state_lines(state: dict, look: _Lookup) -> list[str]:
    cid = str(state.get("character_id") or "")
    char = look.characters.get(cid)
    lines = [
        (
            f"- character {_display(char, cid or 'unknown')} ({cid or '?'}), "
            f"danger {state.get('danger')}, wave {state.get('wave')}, gold {state.get('gold')}"
        )
    ]
    if char:
        bonus = {
            k: char.get(k)
            for k in ("flat_bonuses", "gain_modifiers", "special_effects")
            if char.get(k)
        }
        if bonus:
            lines.append(f"- character traits: {json.dumps(bonus, ensure_ascii=False)}")
    recent = [r for r in state.get("recent") or [] if isinstance(r, dict)]
    if state.get("hp") is not None:
        lines.append(f"- hp {state.get('hp')}/{state.get('max_hp')}")
    elif recent and recent[-1].get("hp") is not None:
        last = recent[-1]
        lines.append(f"- hp {last.get('hp')}/{last.get('max_hp')} at the last wave snapshot")
    stats = state.get("stats") or {}
    nonzero = ", ".join(f"{k} {_num(v)}" for k, v in sorted(stats.items()) if v)
    lines.append(f"- stats: {nonzero or 'all zero'}")
    weapons = [
        f"{w.get('id')} ({w.get('type')}"
        + (f", sets {', '.join(w.get('set_ids') or [])}" if w.get("set_ids") else "")
        + ")"
        for w in state.get("weapons") or []
        if isinstance(w, dict)
    ]
    lines.append(f"- weapons: {'; '.join(weapons) or 'none'}")
    items = [
        f"{i.get('id')} x{i.get('count', 1)}"
        for i in state.get("items") or []
        if isinstance(i, dict)
    ]
    lines.append(f"- items: {', '.join(items) or 'none'}")
    shop = [s for s in state.get("shop") or [] if isinstance(s, dict)]
    if shop:
        lines.append("- shop slots (slot numbers are the shop's, not option_index):")
        for s in shop:
            lock = ", locked" if s.get("locked") else ""
            lines.append(
                f"  - slot {s.get('index')}: {s.get('id')} ({s.get('kind')}) price "
                f"{s.get('price')}, advisor score {_num(s.get('advisor_score'))}{lock}"
            )
    if state.get("unlocks_this_run"):
        lines.append(f"- challenges completed this run: {', '.join(state['unlocks_this_run'])}")
    if recent:
        lines.append(f"- recent telemetry (last {min(len(recent), RECENT_SHOWN)} snapshots):")
        lines.extend("  - " + json.dumps(r, ensure_ascii=False) for r in recent[-RECENT_SHOWN:])
    lines.append(f"- plan in effect: {state.get('plan_id') or '?'}")
    return lines


def _option_lines(request: dict, state: dict, look: _Lookup) -> list[str]:
    options = [o for o in request.get("options") or [] if isinstance(o, dict)]
    if not options:
        if request.get("kind") == "checkpoint":
            return ["No options at a checkpoint: answer `skip` or `revise_plan`."]
        return ["No options were offered."]
    gold = state.get("gold")
    lines: list[str] = []
    for o in options:
        oid = str(o.get("id") or "")
        head = f"- option_index {o.get('index')}: {oid}"
        if "stat" in o and "price" not in o:  # a level-up upgrade
            lines.append(
                f"{head}: {o.get('stat')} {_signed(o.get('value'))}, "
                f"advisor score {_num(o.get('score'))}"
            )
            continue
        price = o.get("price")
        rec = look.record(oid)
        afford = ""
        if isinstance(price, int) and isinstance(gold, int) and price > gold:
            afford = f" (unaffordable with gold {gold})"
        lines.append(
            f"{head} ({o.get('kind')}) {_display(rec, oid)}, price {price}{afford}, "
            f"advisor score {_num(o.get('score'))}"
        )
        if rec is None:
            lines.append(f"  unknown item {oid}")
            continue
        lines.append(f"  record: {_compact(rec)}")
        lines.extend(_set_lines(rec, look))
    return lines


def _plan_lines(plan: dict) -> list[str]:
    if not plan:
        return ["No plan file: the bot's built-in plan for this character applies."]
    text = json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
    if len(text) > PLAN_MAX_CHARS:
        rest = len(text) - PLAN_MAX_CHARS
        text = text[:PLAN_MAX_CHARS] + "\n" + PLAN_TRUNCATED.format(n=rest)
    return ["```json", text, "```"]


def _slugify(text: str) -> str:
    return _SLUG_JUNK.sub("-", text.lower()).strip("-")


def _knowledge_lines(
    request: dict, state: dict, knowledge: dict[str, str], look: _Lookup
) -> list[str]:
    cid = str(state.get("character_id") or "")
    char = look.characters.get(cid) or {}
    terms = [char.get("name"), char.get("display_name")]
    for o in request.get("options") or []:
        rec = look.record(str(o.get("id") or "")) if isinstance(o, dict) else None
        if rec:
            terms += [rec.get("name"), rec.get("display_name")]
    terms = list(dict.fromkeys(t for t in terms if isinstance(t, str) and t.strip()))
    char_slug = _slugify(cid) if cid else None
    slugs = sorted(knowledge, key=lambda s: (s != char_slug, s))
    lines: list[str] = []
    used = 0
    for slug in slugs:
        text = excerpt(knowledge[slug], terms)
        if not text:
            continue
        if used + len(text) > KNOWLEDGE_MAX_CHARS:
            continue  # a smaller excerpt further on may still fit
        used += len(text)
        lines += [f"[{slug}]", text, ""]
    return lines[:-1] if lines else ["none"]


def _past_lines(experience: list[dict]) -> list[str]:
    if not experience:
        return ["none yet"]
    lines = []
    for r in experience:
        conf = r.get("confidence")
        conf_s = f" (confidence {_num(conf)})" if conf is not None else ""
        lines.append(
            f"- run {r.get('run_id')} wave {r.get('wave')} {r.get('kind')}: chose "
            f"{r.get('chosen')} via {r.get('source')}{conf_s} -> {r.get('outcome')}, "
            f"death_wave {r.get('death_wave')}, hp_next_wave {r.get('hp_next_wave')}, "
            f"kept_to_end {r.get('kept_to_end')}"
        )
    return lines


ANSWER_FORMAT = (
    "Answer with only one JSON object matching the Decision schema in the system prompt; "
    "`option_index` indexes the Options list above (the request's `options[]`), never the "
    "shop slot `index` in the State section."
)


def build(
    request: dict,
    state: dict,
    plan: dict,
    dataset: dict,
    unlock_state: dict,
    knowledge: dict[str, str],
    experience: list[dict],
) -> str:
    """The user message for one decision request (see the module docstring)."""
    request, state, plan = request or {}, state or {}, plan or {}
    look = _Lookup(dataset or {})
    kind = request.get("kind") or "?"
    sections = [
        (
            "## Objective",
            [
                f"Decision: {kind} (screen {request.get('screen') or kind}).",
                *_objective(state, plan, unlock_state or {}),
            ],
        ),
        ("## State", _state_lines(state, look)),
        ("## Options", _option_lines(request, state, look)),
        ("## Plan", _plan_lines(plan)),
        ("## Relevant knowledge", _knowledge_lines(request, state, knowledge or {}, look)),
        ("## Past decisions", _past_lines(experience or [])),
        ("## Answer format", [ANSWER_FORMAT]),
    ]
    return "\n\n".join(h + "\n\n" + "\n".join(body) for h, body in sections) + "\n"
