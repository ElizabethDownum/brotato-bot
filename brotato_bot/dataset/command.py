"""CLI: ``dataset build [--pck PATH] [--out PATH]`` unpacks the pck and builds the dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from brotato_bot import cli, paths
from brotato_bot.dataset import build, unpack, version


def _build(args: argparse.Namespace) -> int:
    p = paths.load()
    pck = Path(args.pck) if args.pck else p.pck
    out = Path(args.out) if args.out else p.data_dir / "brotato.json"
    extracted = p.data_dir / "extracted"
    # Detect the version first: it is a cheap scan, and a pck without one should
    # fail before the full unpack.
    try:
        game_version = version.detect_game_version(pck)
        print(f"Game version: {game_version}")
        unpack.unpack(pck, extracted)
        build.build_dataset(extracted, out, game_version)
    except ValueError as exc:
        print(f"dataset build failed: {exc}", file=sys.stderr)
        return 1
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("dataset", help="game-data extraction and dataset build")
    sub = parser.add_subparsers(dest="dataset_command", required=True)
    b = sub.add_parser("build", help="unpack the pck to data/extracted/ and write brotato.json")
    b.add_argument("--pck", default=None, help="Brotato.pck (default: paths.pck)")
    b.add_argument("--out", default=None, help="output JSON (default: <data_dir>/brotato.json)")
    b.set_defaults(func=_build)


cli.COMMANDS["dataset"] = register
