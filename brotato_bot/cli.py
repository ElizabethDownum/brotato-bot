"""Argparse shell. Later tasks add commands by inserting into COMMANDS.

A command is a callable ``register(subparsers) -> None`` that adds a subparser and calls
``parser.set_defaults(func=handler)`` where ``handler(args) -> int``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

COMMANDS: dict[str, Callable] = {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brotato_bot")
    sub = parser.add_subparsers(dest="command")
    for name in sorted(COMMANDS):
        COMMANDS[name](sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(args) or 0)


def _register_builtin_commands() -> None:
    # Command modules add themselves to COMMANDS on import; import them before parsing.
    from brotato_bot.dataset import command, unlock_command  # noqa: F401
    from brotato_bot.knowledge import command as knowledge_command  # noqa: F401


_register_builtin_commands()
