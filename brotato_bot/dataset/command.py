"""CLI: ``dataset build [--pck PATH] [--dlc-pck PATH|none] [--out PATH]``.

Unpacks the base pck, then the Abyssal Terrors DLC pck over it (a missing DLC pck is
skipped with a message), and builds the dataset from the merged tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.dataset import build, unpack, version


def _dlc_pck(arg: str | None, default: Path) -> Path | None:
    if arg is None:
        return default
    if arg.lower() == "none":
        return None
    return Path(arg)


def _build(args: argparse.Namespace) -> int:
    p = paths.load()
    pck = Path(args.pck) if args.pck else p.pck
    dlc_pck = _dlc_pck(args.dlc_pck, p.dlc_pck)
    out = Path(args.out) if args.out else p.data_dir / "brotato.json"
    extracted = p.data_dir / "extracted"
    # Detect the version first: it is a cheap scan, and a pck without one should
    # fail before the full unpack. The version always comes from the base pck.
    try:
        game_version = version.detect_game_version(pck)
        print(f"Game version: {game_version}")
        unpack.unpack(pck, extracted)
        print(f"Unpacked base pck: {pck}")
        # The DLC goes on top of the base, as the game mounts it: same-named files
        # are replaced, everything else is kept.
        if dlc_pck is not None:
            if dlc_pck.is_file():
                unpack.unpack(dlc_pck, extracted)
                print(f"Unpacked DLC pck: {dlc_pck}")
            else:
                print(f"DLC pck not found: {dlc_pck} (skipping)")
        build.build_dataset(extracted, out, game_version)
    except ValueError as exc:
        print(f"dataset build failed: {exc}", file=sys.stderr)
        return 1
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("dataset", help="game-data extraction and dataset build")
    sub = parser.add_subparsers(dest="dataset_command", required=True)
    b = sub.add_parser("build", help="unpack the pck(s) to data/extracted/ and write brotato.json")
    b.add_argument("--pck", default=None, help="Brotato.pck (default: paths.pck)")
    b.add_argument(
        "--dlc-pck",
        default=None,
        help="DLC pck unpacked over the base (default: paths.dlc_pck; 'none' skips it)",
    )
    b.add_argument("--out", default=None, help="output JSON (default: <data_dir>/brotato.json)")
    b.set_defaults(func=_build)


cli.COMMANDS["dataset"] = register
