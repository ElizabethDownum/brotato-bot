"""CLI: ``knowledge fetch [--only SLUG] [--characters]``.

Reads ``<knowledge_dir>/sources.json`` and refreshes ``<knowledge_cache>/<slug>.md``.
``--characters`` first appends one wiki source per character in
``<data_dir>/brotato.json`` (deduplicated by slug) and saves sources.json.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse

from brotato_bot import cli, paths
from brotato_bot.fsutil import atomic_write_json, read_json
from brotato_bot.knowledge import cache, wiki

# Pause between live requests so a full refresh stays polite to the wiki.
REQUEST_PAUSE_S = 0.5


def default_fetch(source: dict) -> str:
    time.sleep(REQUEST_PAUSE_S)
    if source["kind"] == "wiki":
        return wiki.fetch_page(source["ref"])
    scheme = urllib.parse.urlparse(source["ref"]).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"unsupported url scheme {scheme!r}")
    return wiki.http_get(source["ref"]).decode("utf-8", errors="replace")


def _fetch(args: argparse.Namespace) -> int:
    p = paths.load()
    sources_path = p.knowledge_dir / "sources.json"
    try:
        sources = read_json(sources_path)
    except (OSError, ValueError) as exc:
        print(f"knowledge fetch: cannot read {sources_path}: {exc}")
        return 1
    if args.characters:
        dataset_path = p.data_dir / "brotato.json"
        if not dataset_path.is_file():
            print(
                f"{dataset_path} not found; run `dataset build` first. "
                "Skipping character pages."
            )
        else:
            try:
                dataset = read_json(dataset_path)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"cannot read {dataset_path}: {exc}; skipping character pages.")
            else:
                merged = cache.merge_sources(sources, cache.character_sources(dataset))
                added = len(merged) - len(sources)
                if added:
                    atomic_write_json(sources_path, merged)
                print(f"Character sources: {added} added to {sources_path}")
                sources = merged
    if args.only:
        selected = [s for s in sources if s.get("slug") == args.only]
        if not selected:
            print(f"knowledge fetch: no source with slug {args.only!r}")
            return 1
    else:
        selected = sources
    results = cache.refresh(selected, p.knowledge_cache, default_fetch)
    failed = [r for r in results if not r.ok]
    for r in results:
        print(f"{'ok ' if r.ok else 'ERR'} {r.slug}" + (f": {r.error}" if r.error else ""))
    print(f"{len(results) - len(failed)} cached, {len(failed)} failed -> {p.knowledge_cache}")
    return 1 if failed else 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("knowledge", help="wiki and guide knowledge cache")
    sub = parser.add_subparsers(dest="knowledge_command", required=True)
    f = sub.add_parser("fetch", help="refresh knowledge/cache/ from knowledge/sources.json")
    f.add_argument("--only", default=None, metavar="SLUG", help="refresh one source by slug")
    f.add_argument(
        "--characters",
        action="store_true",
        help="first add a wiki source per character in data/brotato.json",
    )
    f.set_defaults(func=_fetch)


cli.COMMANDS["knowledge"] = register
