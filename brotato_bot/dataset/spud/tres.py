# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Minimal parser for Godot 3 text resources (.tres).

Only what the build step needs: section headers, ext/sub resource tables,
and the [resource] key/value block with Godot literals parsed to Python.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADER_RE = re.compile(r"^\[(\w+)(?:\s+(.*))?\]$")
_KV_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"|(\w+)\s*=\s*([\w.\-]+)')


@dataclass
class TresDoc:
    ext_resources: dict[int, dict] = field(default_factory=dict)
    sub_resources: dict[int, dict] = field(default_factory=dict)
    resource: dict[str, object] = field(default_factory=dict)


def _parse_header_attrs(attr_str: str) -> dict:
    attrs: dict[str, object] = {}
    for m in _KV_RE.finditer(attr_str):
        if m.group(1) is not None:
            attrs[m.group(1)] = m.group(2)
        else:
            attrs[m.group(3)] = _parse_value(m.group(4))
    return attrs


def _tokenize_value(s: str) -> list[str]:
    tokens, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace() or c == ",":
            i += 1
        elif c in "[]":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = s.index('"', i + 1)
            tokens.append(s[i:j + 1])
            i = j + 1
        else:
            j = i
            depth = 0
            while j < n and not (s[j] in ",[]" and depth == 0):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                j += 1
            tokens.append(s[i:j].strip())
            i = j
    return [t for t in tokens if t != ""]


def _parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return _parse_array(_tokenize_value(raw))[0]
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    m = re.fullmatch(r"(Ext|Sub)Resource\(\s*(\d+)\s*\)", raw)
    if m:
        key = "__ext__" if m.group(1) == "Ext" else "__sub__"
        return {key: int(m.group(2))}
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_array(tokens: list[str], pos: int = 0):
    # tokens[pos] == "["
    result = []
    i = pos + 1
    while i < len(tokens):
        t = tokens[i]
        if t == "]":
            return result, i + 1
        if t == "[":
            inner, i = _parse_array(tokens, i)
            result.append(inner)
        else:
            result.append(_parse_value(t))
            i += 1
    return result, i


def parse_tres(text: str) -> TresDoc:
    doc = TresDoc()
    section = None
    buffer_key = None
    buffer_val: list[str] = []

    def flush_buffer():
        nonlocal buffer_key, buffer_val
        if buffer_key is not None:
            doc.resource[buffer_key] = _parse_value(" ".join(buffer_val).strip())
            buffer_key, buffer_val = None, []

    for line in text.splitlines():
        stripped = line.strip()
        # A header line looks like [name attr=... ]; a resource kv can also
        # start with '[' (an array). Distinguish: headers have no '=' before
        # the first space and are not inside a [resource] value continuation.
        is_header = bool(_HEADER_RE.match(stripped)) and buffer_key is None and not stripped.startswith("[ ")

        if is_header:
            flush_buffer()
            m = _HEADER_RE.match(stripped)
            name = m.group(1).strip()
            attrs = _parse_header_attrs(m.group(2) or "")
            section = name
            if name == "ext_resource":
                doc.ext_resources[attrs["id"]] = {"path": attrs.get("path"), "type": attrs.get("type")}
            elif name == "sub_resource":
                doc.sub_resources[attrs.get("id")] = {"type": attrs.get("type")}
            continue

        if section == "resource" and "=" in stripped and not stripped.startswith("["):
            flush_buffer()
            key, val = stripped.split("=", 1)
            buffer_key = key.strip()
            buffer_val = [val.strip()]
        elif buffer_key is not None and stripped:
            buffer_val.append(stripped)

    flush_buffer()
    return doc
