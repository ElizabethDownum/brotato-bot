# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Format the build timestamp stamped into the dataset as generated_at."""

from __future__ import annotations

from datetime import datetime


def format_generated_at(dt: datetime) -> str:
    """Format a UTC datetime as the ISO8601 form used for generated_at, e.g. '2026-07-05T12:34:56Z'."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
