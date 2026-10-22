import json
from pathlib import Path

from brotato_bot.dataset.keys import generate_hash

FIXTURES = Path(__file__).parent / "fixtures"


def test_generate_hash_matches_save():
    save = json.loads((FIXTURES / "save_min.json").read_text(encoding="utf-8"))
    # 2999934837 was copied from the real profile save's characters_unlocked.
    assert generate_hash("character_well_rounded") in save["characters_unlocked"]
    assert generate_hash("character_well_rounded") == 2999934837


def test_generate_hash_empty_and_unsigned():
    assert generate_hash("") == 5381
    h = generate_hash("x" * 200)  # long input must wrap to 32-bit unsigned
    assert 0 <= h < 2**32
