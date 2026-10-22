# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Extract the game's VERSION constant from the decompiled progress_data.gd singleton."""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r'const VERSION\s*=\s*"([^"]+)"')


def parse_game_version(text: str) -> str | None:
    """Extract the VERSION constant from progress_data.gd source text.

    Returns None if the constant isn't present (e.g. the singleton's format changed).
    """
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None
