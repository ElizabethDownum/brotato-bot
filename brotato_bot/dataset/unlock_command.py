"""CLI: ``unlock-state [--profile N] [--out PATH] [--save PATH] [--translations PATH]``.

Reads the profile save read-only and writes the unlock state JSON (default
``<data_dir>/unlock_state.json``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brotato_bot import cli, fsutil, paths
from brotato_bot.dataset import unlocks


def save_path(save_dir: Path, profile: int) -> Path:
    # ProgressDataLoaderV3 names each profile's save <save_dir>/save_v3_<profile_id>.json.
    return Path(save_dir) / f"save_v3_{profile}.json"


def _run(args: argparse.Namespace) -> int:
    p = paths.load()
    save_file = Path(args.save) if args.save else save_path(p.save_dir, args.profile)
    out = Path(args.out) if args.out else p.data_dir / "unlock_state.json"
    translations = Path(args.translations) if args.translations else p.data_dir / "translations.csv"
    extracted = p.data_dir / "extracted"
    if not save_file.is_file():
        print(f"unlock-state failed: no save file at {save_file}", file=sys.stderr)
        return 1
    if not (extracted / "challenges").is_dir():
        print(
            f"unlock-state failed: no challenges under {extracted} (run dataset build)",
            file=sys.stderr,
        )
        return 1
    save = json.loads(save_file.read_text(encoding="utf-8"))
    graph = unlocks.build_graph(extracted, translations)
    state = unlocks.unlock_state(graph, save, args.profile)
    fsutil.atomic_write_json(out, state)
    chars = state["characters"]
    n_unlocked = sum(1 for c in chars.values() if c["unlocked"])
    print(
        f"profile {args.profile}: {len(graph)} challenges; done {len(state['done'])}, "
        f"open {len(state['open'])}, blocked {len(state['blocked'])}, "
        f"unknown {len(state['unknown'])} (save lists {len(save.get('challenges_completed', []))}); "
        f"characters unlocked {n_unlocked}/{len(chars)}, "
        f"unknown character hashes {len(state['unknown_characters'])}"
    )
    print(f"wrote {out}")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "unlock-state", help="report a profile's challenge and character unlocks"
    )
    parser.add_argument("--profile", type=int, default=0, help="save profile id (default 0)")
    parser.add_argument(
        "--out", default=None, help="output JSON (default: <data_dir>/unlock_state.json)"
    )
    parser.add_argument(
        "--save", default=None, help="save JSON (default: <save_dir>/save_v3_<profile>.json)"
    )
    parser.add_argument(
        "--translations",
        default=None,
        help="key,en translations CSV (default: <data_dir>/translations.csv)",
    )
    parser.set_defaults(func=_run)


cli.COMMANDS["unlock-state"] = register
