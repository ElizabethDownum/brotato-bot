import functools
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from brotato_bot import paths
from brotato_bot.sidecar import claude_cli, decide, loop

RUN_ID = "run1"
BUY = {"action": "buy", "option_index": 1, "confidence": 0.8, "rationale": "smg", "tags": []}
OPTIONS = [
    {"index": 0, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0},
    {"index": 1, "id": "weapon_smg_1", "kind": "weapon", "price": 25, "score": 6.5},
]
RUN_FIXTURE = Path(__file__).parent.parent / "run" / "fixtures" / "run_small.jsonl"


@pytest.fixture
def p(tmp_path):
    return paths.load(
        {
            "APPDATA": str(tmp_path / "appdata"),
            "BROTATO_BOT_MOD_USER_DIR": str(tmp_path / "mod"),
            "BROTATO_BOT_PROJECT_ROOT": str(tmp_path / "project"),
        }
    )


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _request(p, seq, kind="shop", options=OPTIONS, deadline_ms=None, wave=3):
    rid = f"{RUN_ID}-{seq:03}"
    state = {
        "schema_version": 1,
        "kind": kind,
        "run_id": RUN_ID,
        "seq": seq,
        "wave": wave,
        "danger": 0,
        "character_id": "character_well_rounded",
        "hp": 9,
        "max_hp": 15,
        "gold": 30,
        "weapons": [{"id": "weapon_pistol_1", "type": "ranged"}],
        "items": [{"id": "item_coupon", "count": 2}],
        "unlocks_this_run": ["chal_gatherer_1"] if kind == "checkpoint" else [],
        "target_challenge": "chal_gatherer_1",
    }
    _write(p.state_dir / f"{rid}.json", state)
    if deadline_ms is None:
        deadline_ms = int(time.time() * 1000) + 200_000
    req = {
        "id": rid,
        "kind": kind,
        "screen": kind,
        "run_id": RUN_ID,
        "seq": seq,
        "state_path": f"user://brotato-bot/state/{rid}.json",
        "options": options if kind != "checkpoint" else [],
        "deadline_ms": deadline_ms,
    }
    _write(p.requests_dir / f"{rid}.json", req)
    return rid


class FakeDecide:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def __call__(self, request, context, cfg, *, deadline_ms=None):
        self.calls.append(
            {"request": request, "user": context, "cfg": cfg, "deadline_ms": deadline_ms}
        )
        return self.outcome


def _records(p):
    path = p.decisions_dir / f"{RUN_ID}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_poll_handles_request_and_writes_response(p, capsys):
    rid = _request(p, 1)
    fake = FakeDecide(decide.Outcome(BUY, "haiku", []))
    sidecar = loop.Sidecar(p, {}, decide_fn=fake)

    assert sidecar.poll_once() == 1

    assert json.loads((p.responses_dir / f"{rid}.json").read_text(encoding="utf-8")) == BUY
    assert list(p.responses_dir.iterdir()) == [p.responses_dir / f"{rid}.json"]
    assert not (p.requests_dir / f"{rid}.json").exists()
    assert (p.mod_user_dir / "sidecar.alive").is_file()

    (call,) = fake.calls
    assert call["request"]["id"] == rid and call["request"]["options"] == OPTIONS
    assert "## Options" in call["user"] and "weapon_smg_1" in call["user"]
    assert 150_000 < call["deadline_ms"] <= 200_000

    (rec,) = _records(p)
    assert rec["id"] == rid and rec["kind"] == "shop" and rec["screen"] == "shop"
    assert rec["run_id"] == RUN_ID
    assert rec["model"] == "claude-haiku-5-5"
    assert rec["source"] == "haiku" and rec["attempts"] == []
    assert rec["decision"] == BUY and rec["response"] == BUY
    assert rec["character_id"] == "character_well_rounded" and rec["wave"] == 3
    assert rec["options"] == OPTIONS
    assert rec["prompt_sha256"] == hashlib.sha256(call["user"].encode("utf-8")).hexdigest()
    assert rec["ts"].endswith("+00:00") and isinstance(rec["elapsed_ms"], int)

    out = capsys.readouterr().out
    assert f"[{rid}] shop -> buy via haiku in " in out and out.rstrip().endswith(" ms")
    assert sidecar.poll_once() == 0


def test_requests_processed_in_order(p):
    _request(p, 2)
    _request(p, 1)
    fake = FakeDecide(decide.Outcome(BUY, "haiku", []))
    assert loop.Sidecar(p, {}, decide_fn=fake).poll_once() == 2
    assert [c["request"]["id"] for c in fake.calls] == ["run1-001", "run1-002"]
    assert [r["id"] for r in _records(p)] == ["run1-001", "run1-002"]


def test_fallback_writes_no_response_but_logs(p, capsys):
    rid = _request(p, 1)
    attempt = decide.Attempt("claude-haiku-5-5", "haiku", 0, None, "", ["timed out"])
    fake = FakeDecide(decide.Outcome(None, "fallback", [attempt]))

    assert loop.Sidecar(p, {}, decide_fn=fake).poll_once() == 1

    assert not (p.responses_dir / f"{rid}.json").exists()
    assert not (p.requests_dir / f"{rid}.json").exists()
    (rec,) = _records(p)
    assert rec["source"] == "fallback" and rec["decision"] is None and rec["response"] is None
    assert rec["attempts"][0]["errors"] == ["timed out"]
    assert f"[{rid}] shop -> fallback via fallback in " in capsys.readouterr().out


def test_checkpoint_uses_checkpoint_model_and_writes_note(p):
    rid = _request(p, 4, kind="checkpoint", wave=5)
    revise = {
        "action": "revise_plan",
        "plan_patch": {"max_rerolls": 5},
        "confidence": 0.7,
        "rationale": "target done; survive",
        "tags": ["survival"],
    }
    calls = []

    def fake_run(text, *, system_prompt_file, model, schema_path, timeout_s):
        calls.append((model, Path(system_prompt_file).name, timeout_s))
        return claude_cli.CliResult(json.dumps(revise), revise, 0, 5)

    cfg = {"checkpoint_model": "claude-checkpoint-x", "checkpoint_timeout_ms": 120000}
    decide_fn = functools.partial(decide.decide, run=fake_run)

    assert loop.Sidecar(p, cfg, decide_fn=decide_fn).poll_once() == 1

    # checkpoint_timeout_ms (120 s) sets the call timeout: 120 * 0.4 = 48 s.
    assert calls == [("claude-checkpoint-x", "checkpoint.md", 48.0)]
    assert json.loads((p.responses_dir / f"{rid}.json").read_text(encoding="utf-8")) == revise
    (rec,) = _records(p)
    assert rec["model"] == "claude-checkpoint-x" and rec["screen"] == "checkpoint"

    note = (p.runs_out / f"{RUN_ID}-checkpoint.md").read_text(encoding="utf-8")
    assert note.startswith(f"# Checkpoint {RUN_ID} wave 5\n")
    heads = [line for line in note.splitlines() if line.startswith("## ")]
    assert heads == ["## Achieved", "## Remaining potential", "## Plan revision", "## Rationale"]
    assert "chal_gatherer_1" in note.split("## Remaining potential")[0]
    assert '```json\n{\n  "max_rerolls": 5\n}\n```' in note
    assert note.split("## Rationale")[1].strip() == "target done; survive"


def test_auto_next_triggers_on_end_event(p, monkeypatch):
    lines = RUN_FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    run_file = p.runs_in / "20261022-201500-well_rounded-d0.jsonl"
    run_file.parent.mkdir(parents=True)
    # A finished run from before the sidecar started does not trigger.
    old = p.runs_in / "old-run.jsonl"
    old.write_text(lines[0] + lines[-1], encoding="utf-8")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    sidecar = loop.Sidecar(p, {}, decide_fn=FakeDecide(None), auto_next=True)
    assert sidecar.poll_once() == 0 and calls == []

    run_file.write_text("".join(lines[:-1]), encoding="utf-8")
    sidecar.poll_once()
    assert calls == []

    with run_file.open("a", encoding="utf-8") as fh:
        fh.write(lines[-1])
    sidecar.poll_once()
    sidecar.poll_once()

    assert calls == [
        (
            ["claude", "-p", "--model", "claude-sonnet-5-5", "/brotato-next"],
            {"check": False, "cwd": p.project_root},
        )
    ]
    assert (p.runs_out / "20261022-201500-well_rounded-d0.md").is_file()


def test_auto_next_is_off_by_default(p, monkeypatch):
    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: pytest.fail("ran claude"))
    sidecar = loop.Sidecar(p, {}, decide_fn=FakeDecide(None))
    p.runs_in.mkdir(parents=True)
    shutil.copy(RUN_FIXTURE, p.runs_in / "r.jsonl")
    sidecar.poll_once()


def test_expired_request_is_deleted_without_a_call(p, capsys):
    rid = _request(p, 1, deadline_ms=int(time.time() * 1000) - 5000)
    fake = FakeDecide(decide.Outcome(BUY, "haiku", []))
    assert loop.Sidecar(p, {}, decide_fn=fake).poll_once() == 1
    assert fake.calls == []
    assert not (p.requests_dir / f"{rid}.json").exists()
    assert not (p.responses_dir / f"{rid}.json").exists()
    assert f"[{rid}] shop deadline passed" in capsys.readouterr().out


def test_unreadable_request_is_deleted_with_a_warning(p, capsys):
    p.requests_dir.mkdir(parents=True)
    (p.requests_dir / "run1-001.json").write_text("{not json", encoding="utf-8")
    (p.requests_dir / "run1-002.json.tmp").write_text("{}", encoding="utf-8")
    fake = FakeDecide(decide.Outcome(BUY, "haiku", []))
    assert loop.Sidecar(p, {}, decide_fn=fake).poll_once() == 1
    assert fake.calls == []
    assert sorted(f.name for f in p.requests_dir.iterdir()) == ["run1-002.json.tmp"]
    assert "WARNING: [run1-001] unreadable request" in capsys.readouterr().out


def test_run_forever_removes_heartbeat_on_interrupt(p, monkeypatch):
    sidecar = loop.Sidecar(p, {}, decide_fn=FakeDecide(None))

    def interrupt(_s):
        assert (p.mod_user_dir / "sidecar.alive").is_file()
        raise KeyboardInterrupt

    monkeypatch.setattr(loop.time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        sidecar.run_forever()
    assert not (p.mod_user_dir / "sidecar.alive").exists()
