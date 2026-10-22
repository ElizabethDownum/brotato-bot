# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
# tests/test_build_provenance.py
from brotato_bot.dataset.spud.builders.provenance import detect_source


def test_detect_source_defaults_to_base():
    assert detect_source(record={"id": "weapon_pistol"}) == "base"
    assert detect_source(entry={"weapon_id": "weapon_pistol"}) == "base"
    assert detect_source() == "base"
