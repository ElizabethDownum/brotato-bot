# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Resolve Godot translation-CSV strings so records carry human-readable text.

The decompiled CSV (recovered/.assets/resources/translations/translations.csv)
follows Godot 3.x convention: first column is the key, one column per locale.
Resolution is best-effort — a missing table or key falls back to the
slug-derived name so builds without recovered/ still work.
"""

from __future__ import annotations

import csv
import io


def parse_translations_csv(text: str, locale: str = "en") -> dict[str, str]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or locale not in header:
        return {}
    loc_col = header.index(locale)
    out: dict[str, str] = {}
    for row in reader:
        if row and row[0] and len(row) > loc_col:
            out[row[0]] = row[loc_col]
    return out


def resolve_text(tr: dict[str, str] | None, key: object, fallback: str = "") -> str:
    # An empty translation value (partially-localized CSV column) counts as
    # unresolved — fall back rather than surface a blank display_name.
    if tr and isinstance(key, str) and tr.get(key):
        return tr[key]
    return fallback
