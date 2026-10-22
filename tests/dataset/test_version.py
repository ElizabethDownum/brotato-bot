import struct

import pytest

from brotato_bot.dataset import version


def _gd_string(s: str) -> bytes:
    """Godot 3 Variant encoding of a String constant, as it appears in .gdc bytecode."""
    raw = s.encode()
    return struct.pack("<II", 4, len(raw)) + raw + b"\x00" * (-len(raw) % 4)


def test_detect_game_version_picks_highest(tmp_path):
    pck = tmp_path / "fake.pck"
    pck.write_bytes(
        b"GDPC junk" + _gd_string("1.1.13.2") + b"\xff\x00" + _gd_string("1.1.15.4") + b"tail"
    )
    assert version.detect_game_version(pck) == "1.1.15.4"


def test_detect_game_version_sorts_numerically_not_lexically(tmp_path):
    pck = tmp_path / "fake.pck"
    pck.write_bytes(_gd_string("1.1.9.0") + _gd_string("1.1.10.0"))
    assert version.detect_game_version(pck) == "1.1.10.0"


def test_detect_game_version_ignores_unframed_matches(tmp_path):
    # The real pck holds an MP3 encoder tag "LAME3.100.1.8" in raw audio bytes; it is
    # not a Godot String constant and must not win the version sort.
    pck = tmp_path / "fake.pck"
    pck.write_bytes(b"LAME3.100.1.8\xa9 " + _gd_string("1.1.15.4") + b" 127.0.0.1")
    assert version.detect_game_version(pck) == "1.1.15.4"


def test_detect_game_version_raises_when_absent(tmp_path):
    pck = tmp_path / "fake.pck"
    pck.write_bytes(b"GDPC nothing here 1.2.3")
    with pytest.raises(ValueError, match="no game version"):
        version.detect_game_version(pck)
