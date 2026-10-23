# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from __future__ import annotations

from brotato_bot.dataset.spud.builders.localization import resolve_text
from brotato_bot.dataset.spud.tres import parse_tres


def build_set_record(set_data_text: str, count_effect_texts: dict[int, str | list[str]], *,
                     set_id: str, name: str, tr: dict[str, str] | None = None) -> dict:
    d = parse_tres(set_data_text).resource
    bonuses = []
    for count in sorted(count_effect_texts):
        texts = count_effect_texts[count]
        if isinstance(texts, str):  # the old call shape: one effect per count
            texts = [texts]
        effects = []
        for text in texts:
            r = parse_tres(text).resource
            effects.append({"key": r.get("key", ""), "value": r.get("value", 0)})
        if not effects:
            continue
        # "effect" (the first) stays for backward compatibility with older readers;
        # "effects" carries all of them (blunt at 6 weapons has three).
        bonuses.append({"count": count, "effect": effects[0], "effects": effects})
    return {"id": set_id, "name": name,
            "display_name": resolve_text(tr, d.get("name"), name),
            "description": resolve_text(tr, d.get("description")),
            "bonuses": bonuses}
