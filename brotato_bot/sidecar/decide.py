"""The validation ladder that turns a decision prompt into a validated decision.

1. ``haiku``: ``cfg["model"]`` with ``prompts/decide.md``.
2. ``haiku-retry``: same model, the prompt plus ``## Previous answer was invalid`` and the
   validation errors.
3. ``repair``: ``cfg["repair_model"]`` with ``prompts/repair.md``; the user message is the
   original prompt, the malformed answer and its errors.
4. ``fallback``: no decision; the mod times out and its rules decide.

A checkpoint request uses ``cfg["checkpoint_model"]``, ``prompts/checkpoint.md`` and
``checkpoint_timeout_ms`` for steps 1 and 2. Each call may take
``timeout_ms / 1000 * CALL_TIMEOUT_SHARE`` seconds. A CLI that times out or cannot be
started ends the ladder at once (``fallback``): the deadline is spent or no call can
succeed. A non-zero exit or an invalid answer moves to the next step.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from brotato_bot.sidecar import claude_cli, prompt
from brotato_bot.sidecar.schema import SCHEMA_PATH, validate

DEFAULTS: dict[str, Any] = {
    "model": "claude-haiku-5-5",
    "repair_model": "claude-sonnet-5-5",
    "checkpoint_model": "claude-sonnet-5-5",
    "request_timeout_ms": 45000,
    "checkpoint_timeout_ms": 120000,
}
CALL_TIMEOUT_SHARE = 0.4
RAW_MAX_CHARS = 2000
REPAIR_PROMPT = prompt.PROMPTS_DIR / "repair.md"
NO_JSON = "<root>: no JSON object found in the CLI output"


@dataclass
class Attempt:
    model: str
    source_label: str
    elapsed_ms: int
    returncode: int | None
    raw: str
    errors: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    decision: dict | None
    source: str  # "haiku" | "haiku-retry" | "repair" | "fallback"
    attempts: list[Attempt]

    def to_dict(self) -> dict:
        return asdict(self)


class _CliFailed(Exception):
    pass


def settings(cfg: dict | None) -> dict:
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg or {}).items() if v is not None})
    return out


def _user_message(request: dict, context: Any) -> str:
    """``context`` is the built user message, or a dict of ``prompt.build`` keyword
    arguments (``state, plan, dataset, unlock_state, knowledge, experience``)."""
    if isinstance(context, str):
        return context
    return prompt.build(request, **(context or {}))


def _repair_system() -> str:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8").strip()
    return REPAIR_PROMPT.read_text(encoding="utf-8").replace(prompt.SCHEMA_PLACEHOLDER, schema_text)


def _repair_message(original: str, answer: str, errors: list[str]) -> str:
    return (
        "## Original request\n\n"
        + original.rstrip()
        + "\n\n## Malformed answer\n\n"
        + answer[:RAW_MAX_CHARS]
        + "\n\n## Validation errors\n\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n"
    )


def decide(request: dict, context: Any, cfg: dict | None, run=claude_cli.run) -> Outcome:
    """Run the ladder for one request; see the module docstring."""
    s = settings(cfg)
    checkpoint = (request or {}).get("kind") == "checkpoint"
    model = s["checkpoint_model"] if checkpoint else s["model"]
    timeout_ms = s["checkpoint_timeout_ms"] if checkpoint else s["request_timeout_ms"]
    timeout_s = float(timeout_ms) / 1000 * CALL_TIMEOUT_SHARE
    user = _user_message(request, context)
    attempts: list[Attempt] = []

    with tempfile.TemporaryDirectory(prefix="brotato-bot-") as tmp:
        system_name = "checkpoint.md" if checkpoint else "decide.md"
        system_file = Path(tmp) / system_name
        system_file.write_text(prompt.system_prompt(request.get("kind") or ""), encoding="utf-8")
        repair_file = Path(tmp) / "repair.md"
        repair_file.write_text(_repair_system(), encoding="utf-8")

        def attempt(label: str, text: str, use_model: str, sys_file: Path):
            try:
                res = run(
                    text,
                    system_prompt_file=sys_file,
                    model=use_model,
                    schema_path=SCHEMA_PATH,
                    timeout_s=timeout_s,
                )
            except subprocess.TimeoutExpired:
                attempts.append(
                    Attempt(use_model, label, int(timeout_s * 1000), None, "",
                            [f"claude CLI timed out after {timeout_s:g} s"])
                )  # fmt: skip
                raise _CliFailed from None
            except (OSError, subprocess.SubprocessError) as exc:
                attempts.append(
                    Attempt(use_model, label, 0, None, "",
                            [f"claude CLI failed to run: {type(exc).__name__}: {exc}"[:300]])
                )  # fmt: skip
                raise _CliFailed from None
            errors = [] if res.parsed is not None else [NO_JSON]
            if res.returncode != 0:
                errors.insert(0, f"claude CLI exited with code {res.returncode}")
            if not errors:
                errors = validate(res.parsed)
            attempts.append(
                Attempt(use_model, label, res.elapsed_ms, res.returncode,
                        res.raw[:RAW_MAX_CHARS], list(errors))
            )  # fmt: skip
            return res, errors

        try:
            res, errors = attempt("haiku", user, model, system_file)
            if not errors:
                return Outcome(res.parsed, "haiku", attempts)
            retry = user + "\n\n## Previous answer was invalid\n" + "\n".join(errors)
            res, errors = attempt("haiku-retry", retry, model, system_file)
            if not errors:
                return Outcome(res.parsed, "haiku-retry", attempts)
            fix = _repair_message(user, claude_cli.answer_text(res.raw), errors)
            res, errors = attempt("repair", fix, s["repair_model"], repair_file)
            if not errors:
                return Outcome(res.parsed, "repair", attempts)
        except _CliFailed:
            pass
    return Outcome(None, "fallback", attempts)
