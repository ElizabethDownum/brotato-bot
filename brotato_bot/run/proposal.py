"""Proposal files written by the ``brotato-next`` skill: ``proposals/<date>-<nnn>.md``.

A proposal has these headings in this order: ``# Proposal N``, ``## Target``,
``## Next run``, ``## Plan``, ``## Why``, ``## Risk``, ``## Stagnation check``. ``## Plan`` holds
exactly one fenced JSON plan file. ``## Next run`` holds exactly three bullets, in the order
character, danger, target.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from brotato_bot import cli, paths
from brotato_bot.fsutil import read_json
from brotato_bot.run import prepare

SECTIONS = ("## Target", "## Next run", "## Plan", "## Why", "## Risk", "## Stagnation check")
_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-(\d+)\.md")
_TITLE = re.compile(r"# Proposal (\d+)")
_FENCED_JSON = re.compile(r"```json[ \t]*\n(.*?)```", re.DOTALL)
_RUN_BULLET = re.compile(r"- (character|danger|target): (.+)")
_RUN_KEYS = ["character", "danger", "target"]
_PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*>")


def next_path(proposals_dir: Path, today: date) -> Path:
    """``<today>-<n:03>.md``, n one past the highest number in any date's proposal file."""
    numbers = [
        int(m.group(1)) for p in Path(proposals_dir).glob("*.md") if (m := _NAME.fullmatch(p.name))
    ]
    return Path(proposals_dir) / f"{today.isoformat()}-{max(numbers, default=0) + 1:03d}.md"


def load_unlock_state(path: Path) -> dict:
    """The profile's unlock state; ValueError (naming the fix) when it is not built yet."""
    if not Path(path).is_file():
        raise ValueError(f"{path} is missing; run unlock-state --profile 1 first")
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")  # noqa: TRY004
    return data


def _section(markdown: str, heading: str) -> str | None:
    """The text under ``heading`` up to the next ``## `` heading, or None when absent."""
    m = re.search(
        rf"^{re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)",
        markdown.replace("\r\n", "\n"),
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1) if m else None


def _headings(markdown: str) -> list[str]:
    """The ``# `` and ``## `` lines outside fenced code blocks."""
    out: list[str] = []
    fenced = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith(("# ", "## ")):
            out.append(line.rstrip())
    return out


def _check_sections(markdown: str) -> list[str]:
    heads = _headings(markdown)
    if not heads or not _TITLE.fullmatch(heads[0]):
        return ["first heading must be '# Proposal <n>'"]
    if tuple(heads[1:]) != SECTIONS:
        return [f"sections must be {', '.join(SECTIONS)} in that order; found {heads[1:]}"]
    return []


def extract_plan(markdown: str) -> dict:
    """The JSON object in the one fenced block under ``## Plan``; ValueError otherwise."""
    body = _section(markdown, "## Plan")
    if body is None:
        raise ValueError("section missing")
    blocks = _FENCED_JSON.findall(body)
    if len(blocks) != 1:
        raise ValueError(f"needs exactly one ```json block, found {len(blocks)}")
    return json.loads(blocks[0])


def next_run(markdown: str) -> dict:
    """``{character_id, danger, target}`` from ``## Next run``; target is None for ``none``."""
    body = _section(markdown, "## Next run")
    if body is None:
        raise ValueError("section missing")
    bullets = []
    for line in (ln.strip() for ln in body.splitlines()):
        if not line:
            continue
        m = _RUN_BULLET.fullmatch(line)
        if m is None:
            raise ValueError(f"line is not a character, danger or target bullet: {line!r}")
        bullets.append((m.group(1), m.group(2)))
    if [key for key, _ in bullets] != _RUN_KEYS:
        raise ValueError("needs exactly three bullets, character, danger and target, in that order")
    fields = dict(bullets)
    try:
        danger = int(fields["danger"])
    except ValueError:
        raise ValueError(f"danger must be an integer: {fields['danger']!r}") from None
    target = fields["target"]
    return {
        "character_id": fields["character"],
        "danger": danger,
        "target": None if target == "none" else target,
    }


def _target_errors(target: str, character: str, unlock_state: dict) -> list[str]:
    errors = []
    if target not in unlock_state.get("open", []):
        where = next(
            (name for name in ("done", "blocked") if target in unlock_state.get(name, [])),
            "unknown",
        )
        errors.append(f"## Next run: target {target} is not open (listed as {where})")
    progress = unlock_state.get("progress")
    info = progress.get(target) if isinstance(progress, dict) else None
    need = info.get("requires_character") if isinstance(info, dict) else None
    if need is not None and need != character:
        errors.append(f"## Next run: target {target} needs character {need}, not {character}")
    return errors


def validate(
    markdown: str, unlock_state: dict[str, Any], file_name: str | None = None
) -> list[str]:
    """Problems with a proposal; an empty list means it is valid.

    ``file_name`` (the proposal's file name) enables the check that the title number matches it.
    """
    markdown = markdown.replace("\r\n", "\n")
    errors = _check_sections(markdown)
    heads = _headings(markdown)
    title = _TITLE.fullmatch(heads[0]) if heads else None
    named = _NAME.fullmatch(file_name) if file_name else None
    if title and named and int(title.group(1)) != int(named.group(1)):
        errors.append(
            f"title is Proposal {int(title.group(1))} but the file is number {int(named.group(1))}"
        )
    for left in dict.fromkeys(_PLACEHOLDER.findall(markdown)):
        errors.append(f"unfilled placeholder {left}")
    plan = None
    try:
        plan = extract_plan(markdown)
        prepare.validate_plan(plan)
    except ValueError as exc:
        errors.append(f"## Plan: {exc}")
        plan = None
    try:
        run = next_run(markdown)
    except ValueError as exc:
        errors.append(f"## Next run: {exc}")
        return errors
    character = run["character_id"]
    if plan is not None and plan["character_id"] != character:
        errors.append(
            f"## Next run: character {character} is not the plan's character {plan['character_id']}"
        )
    characters = unlock_state.get("characters")
    entry = characters.get(character) if isinstance(characters, dict) else None
    if isinstance(entry, dict) and entry.get("unlocked") is False:
        errors.append(f"character {character} is locked on the bot profile")
    if run["target"] is not None:
        errors.extend(_target_errors(run["target"], character, unlock_state))
    return errors


def _next_path(args: argparse.Namespace) -> int:
    print(next_path(paths.load().proposals_dir, date.today()))
    return 0


def _validate(args: argparse.Namespace) -> int:
    p = paths.load()
    try:
        markdown = Path(args.file).read_text(encoding="utf-8")
        unlock_state = load_unlock_state(p.data_dir / "unlock_state.json")
    except (OSError, ValueError) as exc:
        print(f"proposal: {exc}")
        return 1
    errors = validate(markdown, unlock_state, Path(args.file).name)
    if errors:
        for e in errors:
            print(e)
        return 1
    print("ok")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("proposal", help="proposal files written by brotato-next")
    sub = parser.add_subparsers(dest="proposal_command", required=True)
    check = sub.add_parser("validate", help="check a proposal; prints ok or one error per line")
    check.add_argument("file", metavar="FILE")
    check.set_defaults(func=_validate)
    nxt = sub.add_parser("next-path", help="print the path for today's next proposal")
    nxt.set_defaults(func=_next_path)


cli.COMMANDS["proposal"] = register
