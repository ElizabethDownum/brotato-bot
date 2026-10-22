"""Knowledge cache: fetched wiki/guide text stored as ``<slug>.md`` with front matter.

Each cached file starts with::

    ---
    source: <ref>
    fetched_at: <iso>
    ---

A source is ``{"slug": str, "kind": "wiki" | "url", "ref": str}``. A failed or empty
fetch never touches the existing file; writes are atomic (tmp + rename).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brotato_bot.fsutil import atomic_write_text

KINDS = ("wiki", "url")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PARAGRAPH_SPLIT = re.compile(r"\n[ \t]*\n")
# Game display name -> wiki page title, where they differ (checked 2026-10-22).
WIKI_TITLE_OVERRIDES = {"One Arm": "One Armed"}

Fetch = Callable[[dict], str]


@dataclass(frozen=True)
class Result:
    slug: str
    path: Path | None
    ok: bool
    error: str | None = None


def front_matter(source: str, fetched_at: str) -> str:
    return f"---\nsource: {source}\nfetched_at: {fetched_at}\n---\n"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body). Text without a leading ``---`` block has empty metadata."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    close = end + len("\n---")
    if close < len(text) and text[close] != "\n":
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, text[close + 1 :]


def _validate(source: Any) -> str | None:
    if not isinstance(source, dict):
        return "source is not an object"
    slug = source.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        return f"bad slug {slug!r}"
    if source.get("kind") not in KINDS:
        return f"bad kind {source.get('kind')!r}"
    if not isinstance(source.get("ref"), str) or not source["ref"].strip():
        return "missing ref"
    return None


def refresh(sources: list[dict], cache_dir: Path, fetch: Fetch) -> list[Result]:
    """Fetch every source into ``cache_dir/<slug>.md``; one failure never stops the rest."""
    cache_dir = Path(cache_dir)
    results: list[Result] = []
    for source in sources:
        slug = source.get("slug", "?") if isinstance(source, dict) else "?"
        problem = _validate(source)
        if problem:
            results.append(Result(str(slug), None, False, problem))
            continue
        path = cache_dir / f"{slug}.md"
        try:
            text = fetch(source)
        except Exception as exc:  # noqa: BLE001 - any fetch failure is reported, not raised
            results.append(Result(slug, path, False, f"{type(exc).__name__}: {exc}"))
            continue
        if not isinstance(text, str) or not text.strip():
            results.append(Result(slug, path, False, "empty response; cache left unchanged"))
            continue
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        body = text if text.endswith("\n") else text + "\n"
        atomic_write_text(path, front_matter(source["ref"], stamp) + body)
        results.append(Result(slug, path, True))
    return results


def load_all(cache_dir: Path) -> dict[str, str]:
    """Return ``{slug: full file text}`` for every ``*.md`` in ``cache_dir``."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(cache_dir.glob("*.md"))}


def excerpt(text: str, terms: list[str], max_chars: int = 1500) -> str:
    """Paragraphs of the body containing any term (case-insensitive), in order, truncated."""
    needles = [t.lower() for t in terms if t and t.strip()]
    if not needles:
        return ""
    _, body = split_front_matter(text)
    picked = []
    for para in _PARAGRAPH_SPLIT.split(body.replace("\r\n", "\n")):
        para = para.strip()
        if para and any(n in para.lower() for n in needles):
            picked.append(para)
    out = "\n\n".join(picked)
    return out[:max_chars].rstrip() if len(out) > max_chars else out


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def character_sources(dataset: dict) -> list[dict]:
    """One ``wiki`` source per character; the wiki page title is the display name."""
    out = []
    for ch in dataset.get("characters") or []:
        name = (ch.get("name") or "").strip()
        if not name:
            continue
        slug = _slugify(ch.get("id") or ("character_" + name))
        ref = WIKI_TITLE_OVERRIDES.get(name, name)
        out.append({"slug": slug, "kind": "wiki", "ref": ref})
    return out


def merge_sources(base: Iterable[dict], extra: Iterable[dict]) -> list[dict]:
    """``base`` followed by entries of ``extra`` whose slug is new; first slug wins."""
    merged = list(base)
    seen = {s.get("slug") for s in merged}
    for s in extra:
        if s.get("slug") not in seen:
            merged.append(s)
            seen.add(s.get("slug"))
    return merged
