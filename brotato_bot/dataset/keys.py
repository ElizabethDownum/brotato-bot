"""The game's ``Keys.generate_hash``: the integer ids the save file stores.

``Keys.generate_hash(text)`` returns ``text.hash()`` (``Keys.empty_hash`` for the empty
string, the same value). Godot 3's ``String.hash()`` is djb2 over the string's characters
with 32-bit unsigned wrap-around: ``h = 5381; h = h * 33 + c``. Godot 3 stores characters
as ``wchar_t`` (UTF-16 code units on Windows), so a non-BMP character is hashed as its
surrogate pair; every game id is ASCII, where the distinction never arises.
"""

from __future__ import annotations

_MASK = 0xFFFFFFFF


def generate_hash(s: str) -> int:
    h = 5381
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h = ((h << 5) + h + (data[i] | data[i + 1] << 8)) & _MASK
    return h
