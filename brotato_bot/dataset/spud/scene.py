# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Read a named [node ...] block from a Godot 3 .tscn scene.

parse_tres only captures the [resource] section; enemy attack parameters live
in a [node name="AttackBehavior"] section, so this small reader extracts one
named node's key/value block. Godot literals are parsed with tres._parse_value.
"""

from __future__ import annotations

import re

from brotato_bot.dataset.spud.tres import _parse_value

_NODE_NAME_RE = re.compile(r'^\[node\s+.*\bname="([^"]+)"')


def parse_scene_node(text: str, node_name: str) -> dict[str, object]:
    result: dict[str, object] = {}
    in_target = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if in_target:
                break  # a new section ends the target node
            m = _NODE_NAME_RE.match(stripped)
            in_target = bool(m and m.group(1) == node_name)
            continue
        if in_target and "=" in stripped:
            key, val = stripped.split("=", 1)
            result[key.strip()] = _parse_value(val.strip())
    return result
