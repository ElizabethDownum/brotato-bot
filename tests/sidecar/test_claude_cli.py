import json
import subprocess
from pathlib import Path

from brotato_bot.sidecar import claude_cli
from brotato_bot.sidecar.schema import SCHEMA_PATH

DECISION = {"action": "buy", "option_index": 0, "confidence": 0.7, "rationale": "smg", "tags": []}


def _completed(stdout: str, returncode: int = 0):
    def runner(cmd, **kwargs):
        runner.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    runner.calls = []
    return runner


def test_parse_cli_output_accepts_string_or_object():
    as_object = json.dumps({"type": "result", "structured_output": DECISION, "result": ""})
    as_string = json.dumps({"type": "result", "structured_output": json.dumps(DECISION)})
    in_result = json.dumps({"type": "result", "result": json.dumps(DECISION)})
    fenced = json.dumps({"result": "```json\n" + json.dumps(DECISION) + "\n```"})
    for raw in (as_object, as_string, in_result, fenced):
        assert claude_cli.parse_output(raw) == DECISION


def test_parse_cli_output_rejects_garbage():
    assert claude_cli.parse_output("") is None
    assert claude_cli.parse_output("not json") is None
    assert claude_cli.parse_output(json.dumps({"result": "I think you should buy"})) is None
    assert claude_cli.parse_output(json.dumps([1, 2])) is None
    assert claude_cli.parse_output(json.dumps({"is_error": True, "result": "boom"})) is None


def test_run_builds_expected_command(tmp_path: Path):
    system = tmp_path / "system.md"
    system.write_text("sys", encoding="utf-8")
    runner = _completed(json.dumps({"structured_output": DECISION}))
    res = claude_cli.run(
        "the prompt",
        system_prompt_file=system,
        model="claude-haiku-5-5",
        schema_path=SCHEMA_PATH,
        timeout_s=18.0,
        runner=runner,
    )
    ((cmd, kwargs),) = runner.calls
    schema_text = claude_cli.schema_arg(SCHEMA_PATH)
    assert cmd == [
        "claude",
        "-p",
        "--model",
        "claude-haiku-5-5",
        "--effort",
        "medium",
        "--output-format",
        "json",
        "--json-schema",
        schema_text,
        "--system-prompt-file",
        str(system),
        "--max-turns",
        "2",
        "--allowedTools",
        "",
        "--tools",
        "",
        "--setting-sources",
        "",
        "--no-session-persistence",
    ]
    assert kwargs["input"] == "the prompt"
    assert kwargs["timeout"] == 18.0
    assert kwargs.get("shell", False) is False
    assert res.parsed == DECISION and res.returncode == 0 and res.elapsed_ms >= 0


def test_schema_arg_drops_top_level_combinators():
    # The CLI sends the schema as a tool input_schema; the API rejects a top-level allOf.
    full = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "allOf" in full
    arg = json.loads(claude_cli.schema_arg(SCHEMA_PATH))
    assert not {"allOf", "anyOf", "oneOf"} & arg.keys()
    assert arg["properties"] == full["properties"] and arg["required"] == full["required"]
    assert arg["additionalProperties"] is False


def test_run_strips_api_credentials_from_the_cli_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-test")
    monkeypatch.setenv("BROTATO_ENV_PROBE", "kept")
    runner = _completed(json.dumps({"structured_output": DECISION}))
    claude_cli.run(
        "p",
        system_prompt_file=tmp_path / "s.md",
        model="m",
        schema_path=SCHEMA_PATH,
        timeout_s=1.0,
        runner=runner,
    )
    ((_cmd, kwargs),) = runner.calls
    env = kwargs["env"]
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["BROTATO_ENV_PROBE"] == "kept"
