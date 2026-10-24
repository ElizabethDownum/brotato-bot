"""Challenge/unlock graph from the extracted challenge resources, and a profile's state.

``build_graph`` reads ``<extracted>/challenges/*.tres`` and
``<extracted>/dlcs/*/challenges/*.tres`` (one ``ChallengeData`` each);
``unlock_state`` joins it with a profile save (``save_v3_<profile>.json``), whose
``challenges_completed`` and ``characters_unlocked`` hold ``Keys.generate_hash`` ids.

``requires_character``: a challenge whose ``description`` is ``CHAL_CHARACTER_DESC`` is
the "win a run with <character>" challenge. The game completes it on a won run as
``"chal_" + <character name>`` and maps it back to the character via
``my_id.replace("chal_", "character_")``, so it can only progress while playing that
character. Every other challenge is character-agnostic (``requires_character`` is None).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from brotato_bot.dataset.keys import generate_hash
from brotato_bot.dataset.spud.builders.localization import parse_translations_csv
from brotato_bot.dataset.spud.tres import TresDoc, parse_tres

RewardKind = Literal["item", "weapon", "character"]

CHARACTER_CHALLENGE_DESC = "CHAL_CHARACTER_DESC"
# Base-pck rewards live under items/all, weapons and items/characters; a DLC pck
# (dlcs/<dlc>/...) uses items, weapons and characters.
_REWARD_PATH_RE = re.compile(
    r"^res://(?:(?P<base>items/all|weapons|items/characters)"
    r"|dlcs/[^/]+/(?P<dlc>items|weapons|characters))/"
)
_REWARD_KINDS: dict[str, RewardKind] = {
    "items/all": "item",
    "weapons": "weapon",
    "items/characters": "character",
    "items": "item",
    "characters": "character",
}
# Challenge resources: the base tree, then every DLC tree.
_CHALLENGE_GLOBS = ("challenges/*.tres", "dlcs/*/challenges/*.tres")


@dataclass(frozen=True)
class Challenge:
    id: str
    hash: int
    name_key: str
    name_en: str
    desc_en: str
    reward_kind: RewardKind | None
    reward_id: str | None
    stat: str
    number: int  # display argument for the name text only
    value: int  # the completion target the game compares against
    unlocked_by_default: bool
    requires_character: str | None


def _reward(doc: TresDoc) -> tuple[RewardKind | None, str | None]:
    ref = doc.resource.get("reward")
    if not isinstance(ref, dict) or "__ext__" not in ref:
        return None, None
    path = (doc.ext_resources.get(ref["__ext__"]) or {}).get("path") or ""
    m = _REWARD_PATH_RE.match(path)
    if not m:
        return None, None
    return _REWARD_KINDS[m.group("base") or m.group("dlc")], Path(path).stem.removesuffix("_data")


def _requires_character(my_id: str, description: str) -> str | None:
    if description == CHARACTER_CHALLENGE_DESC and my_id.startswith("chal_"):
        return "character_" + my_id.removeprefix("chal_")
    return None


def character_id_for_reward(reward_id: str) -> str:
    # Character resources live at items/characters/<name>/<name>_data.tres (base) or
    # dlcs/<dlc>/characters/<name>/<name>_data.tres (DLC), with
    # my_id "character_<name>".
    return "character_" + reward_id


def build_graph(extracted: Path, translations: Path | None = None) -> list[Challenge]:
    """Parse every base and DLC challenge resource under ``extracted``, sorted by id.

    ``translations`` is a ``key,en`` CSV; when it is absent, English text falls back to
    the translation key.
    """
    tr: dict[str, str] = {}
    if translations is not None and Path(translations).is_file():
        tr = parse_translations_csv(Path(translations).read_text(encoding="utf-8-sig"))

    root = Path(extracted)
    files = [path for pattern in _CHALLENGE_GLOBS for path in sorted(root.glob(pattern))]
    graph: list[Challenge] = []
    for path in files:
        doc = parse_tres(path.read_text(encoding="utf-8"))
        res = doc.resource
        my_id = res.get("my_id")
        if not isinstance(my_id, str) or not my_id:
            continue
        name_key = str(res.get("name", ""))
        desc_key = str(res.get("description", ""))
        kind, reward_id = _reward(doc)
        graph.append(
            Challenge(
                id=my_id,
                hash=generate_hash(my_id),
                name_key=name_key,
                name_en=tr.get(name_key) or name_key,
                desc_en=tr.get(desc_key) or desc_key,
                reward_kind=kind,
                reward_id=reward_id,
                stat=str(res.get("stat", "")),
                number=int(res.get("number", 0) or 0),
                value=int(res.get("value", 0) or 0),
                unlocked_by_default=bool(res.get("unlocked_by_default", False)),
                requires_character=_requires_character(my_id, desc_key),
            )
        )
    graph.sort(key=lambda c: c.id)
    return graph


def unlock_state(graph: list[Challenge], save: dict, profile_id: int) -> dict:
    """Split the graph into done/open/blocked for one profile's save dict.

    ``characters`` covers every character the graph names (as a requirement or a
    reward). ``unknown`` lists completed-challenge hashes the graph lacks;
    ``unknown_characters`` lists unlocked-character hashes the graph never names
    (for example DLC characters whose resources are not in the base pck).
    """
    completed = [int(h) for h in save.get("challenges_completed", [])]
    unlocked = [int(h) for h in save.get("characters_unlocked", [])]
    completed_set = set(completed)
    unlocked_set = set(unlocked)
    graph_hashes = {c.hash for c in graph}

    characters: dict[str, dict] = {}
    for c in graph:
        if c.requires_character:
            characters.setdefault(c.requires_character, {"unlocked": False, "unlocked_by": None})
    for c in graph:
        if c.reward_kind == "character" and c.reward_id:
            entry = characters.setdefault(
                character_id_for_reward(c.reward_id), {"unlocked": False, "unlocked_by": None}
            )
            entry["unlocked_by"] = c.id
    for char_id, entry in characters.items():
        entry["unlocked"] = generate_hash(char_id) in unlocked_set
    character_hashes = {generate_hash(cid) for cid in characters}

    done: list[str] = []
    open_: list[str] = []
    blocked: list[str] = []
    progress: dict[str, dict] = {}
    for c in graph:
        if c.hash in completed_set or c.unlocked_by_default:
            done.append(c.id)
            continue
        req = c.requires_character
        if req and not characters[req]["unlocked"]:
            blocked.append(c.id)
        else:
            open_.append(c.id)
        progress[c.id] = {
            "requires_character": req,
            "stat": c.stat,
            "number": c.number,
            "value": c.value,
        }

    return {
        "profile": profile_id,
        "done": done,
        "open": open_,
        "blocked": blocked,
        "unknown": [h for h in dict.fromkeys(completed) if h not in graph_hashes],
        "unknown_characters": [h for h in dict.fromkeys(unlocked) if h not in character_hashes],
        "characters": dict(sorted(characters.items())),
        "progress": progress,
    }


def item_weapon_state(dataset: dict, save: dict) -> dict:
    """``items_unlocked``/``items_locked`` and ``weapons_unlocked``/``weapons_locked``: the
    dataset ids (sorted, weapons once, no tier suffix) whose ``Keys.generate_hash`` is in
    the save's ``items_unlocked`` / ``weapons_unlocked``. The save hashes the base weapon id
    (``weapon_rock``), which the dataset repeats once per tier; checked 2026-10-23: all 197
    item hashes and all 56 weapon hashes matched, none matched a ``_<tier>`` form."""
    out: dict[str, list[str]] = {}
    for kind in ("items", "weapons"):
        have = {int(h) for h in save.get(f"{kind}_unlocked", [])}
        ids = sorted(
            {r["id"] for r in dataset.get(kind) or [] if isinstance(r, dict) and r.get("id")}
        )
        out[f"{kind}_unlocked"] = [i for i in ids if generate_hash(i) in have]
        out[f"{kind}_locked"] = [i for i in ids if generate_hash(i) not in have]
    return out


_FORMAT_ARG = re.compile(r"\{(\d+)\}")


def _fmt(template: str, args: list[str]) -> str:
    return _FORMAT_ARG.sub(
        lambda m: args[int(m.group(1))] if int(m.group(1)) < len(args) else m.group(0), template
    )


def challenge_texts(graph: Iterable[Any], dataset: dict | None = None) -> dict[str, dict]:
    """``{challenge_id: {"name", "description"}}`` in English, formatted as the game does
    (``ChallengeData.get_name_text`` / ``get_description_text``): the name takes the
    challenge's ``number``; a "win a run with" description takes the character's name,
    any other the completion ``value`` and the stat. ``graph`` is ``unlocks.build_graph``.
    """
    chars = {c.get("id"): c for c in (dataset or {}).get("characters") or []}
    out: dict[str, dict] = {}
    for c in graph:
        if c.requires_character:
            who = c.name_en
            if not who or who == c.name_key:
                rec = chars.get(c.requires_character) or {}
                who = rec.get("display_name") or rec.get("name") or c.requires_character
            args = [who]
        else:
            args = [str(c.value), c.stat.removeprefix("stat_").replace("_", " ")]
        out[c.id] = {
            "name": _fmt(c.name_en, [str(c.number)]),
            "description": _fmt(c.desc_en, args),
        }
    return out
