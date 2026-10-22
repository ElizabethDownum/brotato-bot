"""Challenge/unlock graph from the extracted challenge resources, and a profile's state.

``build_graph`` reads ``<extracted>/challenges/*.tres`` (one ``ChallengeData`` each);
``unlock_state`` joins it with a profile save (``save_v3_<profile>.json``), whose
``challenges_completed`` and ``characters_unlocked`` hold ``Keys.generate_hash`` ids.

``requires_character``: a challenge whose ``description`` is ``CHAL_CHARACTER_DESC`` is
the "win a run with <character>" challenge. The game completes it on a won run as
``"chal_" + <character name>`` and maps it back to the character via
``my_id.replace("chal_", "character_")``, so it can only progress while playing that
character. Every other challenge is character-agnostic (``requires_character`` is None).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from brotato_bot.dataset.keys import generate_hash
from brotato_bot.dataset.spud.builders.localization import parse_translations_csv
from brotato_bot.dataset.spud.tres import TresDoc, parse_tres

RewardKind = Literal["item", "weapon", "character"]

CHARACTER_CHALLENGE_DESC = "CHAL_CHARACTER_DESC"
_REWARD_PREFIXES: tuple[tuple[str, RewardKind], ...] = (
    ("res://items/all/", "item"),
    ("res://weapons/", "weapon"),
    ("res://items/characters/", "character"),
)


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
    number: int
    unlocked_by_default: bool
    requires_character: str | None


def _reward(doc: TresDoc) -> tuple[RewardKind | None, str | None]:
    ref = doc.resource.get("reward")
    if not isinstance(ref, dict) or "__ext__" not in ref:
        return None, None
    path = (doc.ext_resources.get(ref["__ext__"]) or {}).get("path") or ""
    for prefix, kind in _REWARD_PREFIXES:
        if path.startswith(prefix):
            return kind, Path(path).stem.removesuffix("_data")
    return None, None


def _requires_character(my_id: str, description: str) -> str | None:
    if description == CHARACTER_CHALLENGE_DESC and my_id.startswith("chal_"):
        return "character_" + my_id.removeprefix("chal_")
    return None


def character_id_for_reward(reward_id: str) -> str:
    # Character resources live at items/characters/<name>/<name>_data.tres with
    # my_id "character_<name>".
    return "character_" + reward_id


def build_graph(extracted: Path, translations: Path | None = None) -> list[Challenge]:
    """Parse every challenge resource under ``extracted/challenges``, sorted by id.

    ``translations`` is a ``key,en`` CSV; when it is absent, English text falls back to
    the translation key.
    """
    tr: dict[str, str] = {}
    if translations is not None and Path(translations).is_file():
        tr = parse_translations_csv(Path(translations).read_text(encoding="utf-8-sig"))

    graph: list[Challenge] = []
    for path in sorted((Path(extracted) / "challenges").glob("*.tres")):
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
        progress[c.id] = {"requires_character": req, "stat": c.stat, "number": c.number}

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
