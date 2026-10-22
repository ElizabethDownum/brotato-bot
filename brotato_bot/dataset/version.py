"""Detect the game version from the raw bytes of a Godot 3 .pck.

The version string ("1.1.15.4") is a String constant in compiled GDScript (.gdc)
bytecode, stored as a Godot Variant: u32 type 4 (STRING), u32 byte length, then the
bytes. Only matches with that framing count, because the raw pck also holds
version-shaped noise (e.g. the MP3 encoder tag "LAME3.100.1.8" inside audio data),
which would otherwise win the version sort.
"""

from __future__ import annotations

import mmap
import re
import struct
from pathlib import Path

_FRAMED_VERSION_RE = re.compile(rb"\x04\x00\x00\x00(.{4})(\d+\.\d+\.\d+\.\d+)", re.DOTALL)


def _key(v: str) -> tuple[int, ...]:
    return tuple(int(part) for part in v.split("."))


def detect_game_version(pck: Path) -> str:
    """Return the highest Variant-framed ``N.N.N.N`` string in ``pck``, version-sorted."""
    found: set[str] = set()
    with open(pck, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for m in _FRAMED_VERSION_RE.finditer(mm):
            (length,) = struct.unpack("<I", m.group(1))
            if length == len(m.group(2)):
                found.add(m.group(2).decode("ascii"))
    if not found:
        raise ValueError(f"no game version string found in {pck}")
    return max(found, key=_key)
