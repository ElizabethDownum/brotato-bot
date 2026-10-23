import io
import json
import sys
from pathlib import Path

from brotato_bot import cli
from brotato_bot.sidecar import prompt

FIXTURE = Path(__file__).parent / "fixtures" / "state_shop.json"
SHOP_BUY = {
    "action": "buy",
    "option_index": 0,
    "confidence": 0.7,
    "rationale": "Smg fits the plan.",
    "tags": ["damage"],
}
CHECKPOINT_SKIP = {
    "action": "skip",
    "confidence": 0.6,
    "rationale": "Plan still fits.",
    "tags": ["target"],
}
# The sentences the brief keeps from plan 3 Task 3 Step 1, matched after whitespace is
# collapsed (the prompt files wrap their lines).
DECIDE_SENTENCES = [
    "Output only one JSON object matching the schema.",
    "Prefer the plan unless an offered option clearly dominates it for this character at this wave.",
    "Never invent items, stats or prices; use only the Options section.",
    "When the objective is an unlock target, weight survival to the wave the challenge needs over damage.",
    "When there is no unlock target, optimise this character's current and prospective build, including pivots the offering justifies.",
]
CHECKPOINT_SENTENCES = [
    "The target has already fired.",
    "The objective is now to optimise this character's run; a `revise_plan` answer must contain only keys from the plan schema.",
]
SHOP_OBJECTIVE_END = "Play this run to complete the target; survive while doing so."


def _stdin(monkeypatch, text):
    # Mirrors the real stdin: a text wrapper over UTF-8 bytes, with .buffer available.
    stream = io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stream)


def _collapsed(name):
    return " ".join((prompt.PROMPTS_DIR / name).read_text(encoding="utf-8").split())


def _state_with_levelup(tmp_path):
    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state["kind"] = "levelup"
    state["levelup_options"] = [
        {"id": "stat_armor", "stat": "stat_armor", "value": 1, "advisor_score": 3.0},
        {"id": "stat_speed", "stat": "stat_speed", "value": 2, "advisor_score": 1.0},
    ]
    path = tmp_path / "state_levelup.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def test_valid_shop_answer_from_stdin_is_ok(monkeypatch, capsys):
    _stdin(monkeypatch, json.dumps(SHOP_BUY))
    assert cli.main(["decide-validate"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_non_ascii_rationale_on_stdin_is_ok(monkeypatch, capsys):
    answer = dict(SHOP_BUY, rationale="Ā gold → damage ✓ (é, ü)")
    _stdin(monkeypatch, json.dumps(answer, ensure_ascii=False))
    assert cli.main(["decide-validate"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_answer_from_file_with_state_is_ok(monkeypatch, capsys, tmp_path):
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps(SHOP_BUY), encoding="utf-8")
    assert (
        cli.main(["decide-validate", str(answer), "--state", str(FIXTURE), "--kind", "shop"]) == 0
    )
    assert capsys.readouterr().out.strip() == "ok"


def test_invalid_json_is_one_prefixed_error_line(monkeypatch, capsys):
    _stdin(monkeypatch, "{not json")
    assert cli.main(["decide-validate"]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("decide-validate: not JSON:")


def test_non_object_state_is_one_error_line(monkeypatch, capsys, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("[]", encoding="utf-8")
    _stdin(monkeypatch, json.dumps(SHOP_BUY))
    assert cli.main(["decide-validate", "--state", str(state), "--kind", "shop"]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert out == [f"decide-validate: {state} is not a JSON object"]


def test_pick_on_a_shop_state_is_rejected_with_the_screen_error(monkeypatch, capsys):
    pick = {"action": "pick", "option_index": 0, "confidence": 0.5, "rationale": "x", "tags": []}
    _stdin(monkeypatch, json.dumps(pick))
    assert cli.main(["decide-validate", "--state", str(FIXTURE), "--kind", "shop"]) == 1
    out = capsys.readouterr().out
    assert "action: 'pick' is not allowed on the shop screen" in out


def test_option_index_outside_the_options_is_rejected(monkeypatch, capsys):
    # The fixture's shop has two offers, so the request's options are indexes 0 and 1.
    bad = dict(SHOP_BUY, option_index=2)
    _stdin(monkeypatch, json.dumps(bad))
    assert cli.main(["decide-validate", "--state", str(FIXTURE), "--kind", "shop"]) == 1
    assert "option_index: 2 is not an index in Options [0, 1]" in capsys.readouterr().out


def test_levelup_pick_with_a_valid_index_is_ok(monkeypatch, capsys, tmp_path):
    state = _state_with_levelup(tmp_path)
    pick = {"action": "pick", "option_index": 1, "confidence": 0.5, "rationale": "x", "tags": []}
    _stdin(monkeypatch, json.dumps(pick))
    assert cli.main(["decide-validate", "--state", str(state), "--kind", "levelup"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_levelup_rejects_buy_with_the_screen_error(monkeypatch, capsys, tmp_path):
    state = _state_with_levelup(tmp_path)
    _stdin(monkeypatch, json.dumps(SHOP_BUY))
    assert cli.main(["decide-validate", "--state", str(state), "--kind", "levelup"]) == 1
    assert "action: 'buy' is not allowed on the levelup screen" in capsys.readouterr().out


def test_state_without_kind_is_a_usage_error(monkeypatch, capsys):
    _stdin(monkeypatch, json.dumps(SHOP_BUY))
    assert cli.main(["decide-validate", "--state", str(FIXTURE)]) == 1
    assert "must be given together" in capsys.readouterr().out


def test_checkpoint_skip_is_ok_and_option_index_is_rejected(monkeypatch, capsys):
    args = ["decide-validate", "--state", str(FIXTURE), "--kind", "checkpoint"]
    _stdin(monkeypatch, json.dumps(CHECKPOINT_SKIP))
    assert cli.main(args) == 0
    capsys.readouterr()
    _stdin(monkeypatch, json.dumps(dict(CHECKPOINT_SKIP, option_index=0)))
    assert cli.main(args) == 1
    assert "option_index: 0 is not an index in Options []" in capsys.readouterr().out


def test_decide_prompt_keeps_the_brief_sentences():
    text = _collapsed("decide.md")
    for sentence in DECIDE_SENTENCES:
        assert sentence in text, sentence
    assert "below 0.4" not in text


def test_checkpoint_prompt_keeps_the_brief_sentences():
    text = _collapsed("checkpoint.md")
    for sentence in CHECKPOINT_SENTENCES:
        assert sentence in text, sentence
    assert "below 0.4" not in text
    assert "Options section" not in text  # there are no options at a checkpoint


def test_checkpoint_objective_says_the_target_fired_and_shop_is_unchanged():
    state = {"target_challenge": "chal_gatherer_1"}
    checkpoint = prompt._objective(state, {}, {}, "checkpoint")
    assert checkpoint[-1].startswith("The target has already fired")
    assert "remaining waves" in checkpoint[-1]
    assert SHOP_OBJECTIVE_END not in checkpoint
    for kind in ("shop", "levelup", ""):
        assert prompt._objective(state, {}, {}, kind)[-1] == SHOP_OBJECTIVE_END
