"""Run one ``claude -p`` call and parse its answer.

The Claude Code CLI is the only model access. Its output is untrusted data: it is parsed
with ``json.loads`` only, and the prompt goes to the child on stdin with a list argv and
no shell.

Installed-CLI notes (Claude Code 2.1.308): ``--json-schema`` takes the schema as JSON
text, not a path, so ``run`` reads ``schema_path`` and passes its compact text. The CLI
sends that schema as a tool ``input_schema``, which the API rejects with ``allOf``,
``anyOf`` or ``oneOf`` at the top level (HTTP 400), so those keys are dropped from the
CLI copy; ``schema.validate`` still enforces the conditional fields they express.
``--system-prompt-file`` and ``--max-turns`` are accepted although ``--help`` omits them.
The structured answer is a call of the CLI's own output tool, which uses a turn: with
``--max-turns 1`` every call ended ``error_max_turns`` (``num_turns`` 2) without
``structured_output``, so ``MAX_TURNS`` is 2.
``--no-session-persistence`` keeps every decision call out of the resumable sessions.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLAUDE = "claude"
MAX_TURNS = "2"
# Top-level keys a tool input_schema may not carry (API 400 "does not support oneOf,
# allOf, or anyOf at the top level"); if/then/else only appear inside allOf here.
_TOP_LEVEL_UNSUPPORTED = ("allOf", "anyOf", "oneOf", "if", "then", "else")
_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


@dataclass(frozen=True)
class CliResult:
    raw: str
    parsed: Any | None
    returncode: int
    elapsed_ms: int


def schema_arg(schema_path: Path) -> str:
    """The ``--json-schema`` value: the schema file's JSON without top-level combinators,
    compacted."""
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    for key in _TOP_LEVEL_UNSUPPORTED:
        schema.pop(key, None)
    return json.dumps(schema, separators=(",", ":"))


def command(*, system_prompt_file: Path, model: str, schema_path: Path) -> list[str]:
    return [
        CLAUDE, "-p",
        "--model", model,
        "--output-format", "json",
        "--json-schema", schema_arg(schema_path),
        "--system-prompt-file", str(system_prompt_file),
        "--max-turns", MAX_TURNS,
        "--allowedTools", "",
        "--no-session-persistence",
    ]  # fmt: skip


def _loads(text: str) -> Any | None:
    """``text`` as JSON, also when wrapped in one markdown code fence; else None."""
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _decision(value: Any) -> Any | None:
    if isinstance(value, str):
        value = _loads(value)
    return value if isinstance(value, dict) else None


def parse_output(raw: str) -> Any | None:
    """The decision object in ``claude -p --output-format json`` output, or None.

    ``structured_output`` wins when present (an object, or a string holding one); else
    ``result`` is parsed as JSON (optionally fenced). Anything else is None.
    """
    envelope = _loads(raw or "")
    if not isinstance(envelope, dict):
        return None
    found = _decision(envelope.get("structured_output"))
    if found is not None:
        return found
    return _decision(envelope.get("result"))


def answer_text(raw: str) -> str:
    """What the model said, for a repair prompt: the structured output or the result text
    when the envelope parses, else the raw output itself."""
    envelope = _loads(raw or "")
    if isinstance(envelope, dict):
        for key in ("structured_output", "result"):
            value = envelope.get(key)
            if value not in (None, ""):
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return raw or ""


def run(
    prompt: str,
    *,
    system_prompt_file: Path,
    model: str,
    schema_path: Path,
    timeout_s: float,
    runner=subprocess.run,
) -> CliResult:
    """One CLI call. ``subprocess.TimeoutExpired`` and ``OSError`` (CLI missing) propagate."""
    cmd = command(system_prompt_file=system_prompt_file, model=model, schema_path=schema_path)
    start = time.monotonic()
    proc = runner(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        shell=False,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    raw = proc.stdout or ""
    return CliResult(
        raw=raw, parsed=parse_output(raw), returncode=proc.returncode, elapsed_ms=elapsed_ms
    )
