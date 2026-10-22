import json
import subprocess

from brotato_bot.sidecar import claude_cli, decide

VALID = {"action": "skip", "confidence": 0.6, "rationale": "save gold", "tags": ["economy"]}
INVALID = {"action": "buy", "confidence": 2, "rationale": "x", "tags": []}
REQUEST = {"id": "r-001", "kind": "shop", "options": [{"index": 0, "id": "item_bag"}]}
CFG = {"request_timeout_ms": 45000}


def _scripted(*outputs):
    """A fake subprocess runner returning each output in turn (an exception is raised)."""

    def runner(cmd, **kwargs):
        runner.calls.append((cmd, kwargs))
        out = outputs[len(runner.calls) - 1]
        if isinstance(out, BaseException):
            raise out
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"structured_output": out}), stderr=""
        )

    runner.calls = []
    return runner


def _run_with(runner):
    def run(prompt, **kw):
        return claude_cli.run(prompt, runner=runner, **kw)

    return run


def _model(cmd):
    return cmd[cmd.index("--model") + 1]


def test_first_valid_answer_is_haiku():
    runner = _scripted(VALID)
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "haiku" and out.decision == VALID and len(out.attempts) == 1
    cmd, kwargs = runner.calls[0]
    assert _model(cmd) == "claude-haiku-5-5"
    assert kwargs["timeout"] == 18.0
    assert kwargs["input"] == "PROMPT"


def test_ladder_retries_then_repairs_then_falls_back():
    runner = _scripted(INVALID, INVALID, INVALID)
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "fallback" and out.decision is None
    assert len(out.attempts) == 3
    assert [a.source_label for a in out.attempts] == ["haiku", "haiku-retry", "repair"]
    assert all(a.errors for a in out.attempts)

    runner = _scripted(INVALID, VALID)
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "haiku-retry" and out.decision == VALID
    retry_input = runner.calls[1][1]["input"]
    assert retry_input.startswith("PROMPT\n\n## Previous answer was invalid\n")
    assert "confidence" in retry_input

    runner = _scripted(INVALID, INVALID, VALID)
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "repair" and out.decision == VALID
    third_cmd, third_kwargs = runner.calls[2]
    assert "--model" in third_cmd and _model(third_cmd) == "claude-sonnet-5-5"
    assert "PROMPT" in third_kwargs["input"] and "confidence" in third_kwargs["input"]
    system_file = third_cmd[third_cmd.index("--system-prompt-file") + 1]
    assert system_file.endswith("repair.md")


def test_timeout_is_fallback():
    runner = _scripted(subprocess.TimeoutExpired(["claude"], 18.0))
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "fallback" and out.decision is None
    assert len(out.attempts) == 1 and out.attempts[0].returncode is None
    assert "timed out" in out.attempts[0].errors[0]


def test_missing_cli_is_fallback():
    runner = _scripted(FileNotFoundError("claude"))
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "fallback" and len(out.attempts) == 1


def test_checkpoint_uses_checkpoint_model_prompt_and_timeout():
    runner = _scripted(VALID)
    req = {"id": "r-002", "kind": "checkpoint", "options": []}
    cfg = {"checkpoint_model": "claude-sonnet-5-5", "checkpoint_timeout_ms": 120000}
    out = decide.decide(req, "PROMPT", cfg, run=_run_with(runner))
    assert out.source == "haiku" and out.attempts[0].model == "claude-sonnet-5-5"
    cmd, kwargs = runner.calls[0]
    assert kwargs["timeout"] == 48.0
    system_file = cmd[cmd.index("--system-prompt-file") + 1]
    assert system_file.endswith("checkpoint.md")


def test_rendered_system_prompt_has_schema_inlined():
    seen = {}

    def runner(cmd, **kwargs):
        path = cmd[cmd.index("--system-prompt-file") + 1]
        with open(path, encoding="utf-8") as fh:
            seen["text"] = fh.read()
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"structured_output": VALID}), stderr=""
        )

    decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert "{{DECISION_SCHEMA}}" not in seen["text"]
    assert '"revise_plan"' in seen["text"]


def test_attempt_raw_is_truncated():
    big = {"structured_output": "x" * 5000}

    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(big), stderr="")

    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(runner))
    assert out.source == "fallback"
    assert all(len(a.raw) <= decide.RAW_MAX_CHARS for a in out.attempts)


def test_outcome_is_json_serialisable():
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(_scripted(VALID)))
    data = json.loads(json.dumps(out.to_dict()))
    assert data["source"] == "haiku" and data["attempts"][0]["model"] == "claude-haiku-5-5"


def test_decide_once_request_uses_option_positions(tmp_path):
    from pathlib import Path

    from brotato_bot.sidecar.command import request_from_state

    fixture = Path(__file__).parent / "fixtures" / "state_shop.json"
    state = json.loads(fixture.read_text(encoding="utf-8"))
    req = request_from_state(state, fixture, "shop", decide.settings({}))
    assert [o["index"] for o in req["options"]] == [0, 1]
    assert [o["id"] for o in req["options"]] == ["weapon_smg_1", "item_bag"]
    assert req["options"][0]["score"] == 6.5 and req["deadline_ms"] == 45000
    assert req["id"] == "20261022-201500-well_rounded-d0-002"
    assert request_from_state(state, fixture, "checkpoint", decide.settings({}))["options"] == []


def test_deadline_skips_steps_that_cannot_finish_in_time():
    now = [0.0]

    def runner(cmd, **kwargs):
        now[0] += 20.0  # each call takes 20 s
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"structured_output": INVALID}), stderr=""
        )

    out = decide.decide(
        REQUEST, "PROMPT", CFG, run=_run_with(runner), deadline_ms=45000, clock=lambda: now[0]
    )
    # 45 s budget, 18 s per call: after 20 s, 25 s are left (retry runs); after 40 s, 5 s
    # are left (< 18 s), so the repair step is skipped.
    assert out.source == "fallback"
    assert [a.source_label for a in out.attempts] == ["haiku", "haiku-retry"]


def test_no_deadline_runs_full_ladder():
    out = decide.decide(REQUEST, "PROMPT", CFG, run=_run_with(_scripted(INVALID, INVALID, VALID)))
    assert out.source == "repair"
