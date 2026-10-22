"""Brotato wiki access through the MediaWiki API (stdlib ``urllib`` only)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

# Confirmed 2026-10-22 with action=query&meta=siteinfo (sitename "Brotato Wiki").
BASE_URL = "https://brotato.wiki.spellsandguns.com"
USER_AGENT = "brotato-bot/0.1 (personal Brotato bot harness; knowledge cache)"
TIMEOUT_S = 30


class WikiError(RuntimeError):
    """The wiki API answered with an error or an unexpected payload."""


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read()


def page_url(title: str) -> str:
    # redirects=1 follows wiki redirects so a renamed page still returns its text.
    return (
        BASE_URL
        + "/api.php?action=parse&page="
        + urllib.parse.quote(title, safe="")
        + "&prop=wikitext&format=json&redirects=1"
    )


def fetch_page(title: str, fetch: Callable[[str], bytes] = http_get) -> str:
    """Return the wikitext of ``title``; ``fetch(url) -> bytes`` does the HTTP GET."""
    raw = fetch(page_url(title))
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise WikiError(f"{title}: response is not JSON") from exc
    if "error" in payload:
        err = payload["error"]
        raise WikiError(f"{title}: {err.get('code')}: {err.get('info')}")
    try:
        return payload["parse"]["wikitext"]["*"]
    except (KeyError, TypeError) as exc:
        raise WikiError(f"{title}: no wikitext in response") from exc
