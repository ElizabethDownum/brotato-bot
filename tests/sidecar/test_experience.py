import json
from pathlib import Path

import pytest

from brotato_bot.run import collect
from brotato_bot.sidecar import experience

RUN_FIXTURES = Path(__file__).parent.parent / "run" / "fixtures"
RUN_ID = "20261022-201500-well_rounded-d0"


def _summary():
    events = collect.parse_jsonl(RUN_FIXTURES / "run_small.jsonl")
    return collect.summarize(events)


def _decision(seq, wave, response, options, run_id=RUN_ID, source="haiku"):
    return {
        "id": f"{run_id}-{seq:03d}",
        "run_id": run_id,
        "kind": "shop",
        "screen": "shop",
        "character_id": "character_well_rounded",
        "wave": wave,
        "options": options,
        "response": response,
        "source": source,
        "ts": "2026-10-22T20:16:31",
    }


def test_experience_query_filters_and_limits(tmp_path):
    log = tmp_path / "experience.jsonl"
    for i in range(5):
        experience.append(
            log, {"character_id": "character_well_rounded", "kind": "shop", "wave": i}
        )
    experience.append(log, {"character_id": "character_mage", "kind": "shop", "wave": 99})
    experience.append(
        log, {"character_id": "character_well_rounded", "kind": "levelup", "wave": 98}
    )
    with log.open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    experience.append(log, {"character_id": "character_well_rounded", "kind": "shop", "wave": 5})

    rows = experience.query(log, "character_well_rounded", "shop", n=3)
    assert [r["wave"] for r in rows] == [3, 4, 5]  # the latest three, oldest first
    assert all(r["character_id"] == "character_well_rounded" for r in rows)
    assert len(experience.query(log, "character_well_rounded", "shop")) == 6
    assert experience.query(tmp_path / "missing.jsonl", "character_well_rounded", "shop") == []
    assert experience.query(log, "character_well_rounded", "shop", n=0) == []


def test_join_outcomes_marks_death_wave(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    smg = [
        {"index": 0, "id": "item_coupon", "kind": "item", "price": 15, "score": 1.0},
        {"index": 1, "id": "weapon_smg_1", "kind": "weapon", "price": 25, "score": 6.5},
    ]
    bag = [{"index": 0, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0}]
    rows = [
        _decision(
            1,
            1,
            {
                "action": "buy",
                "option_index": 1,
                "confidence": 0.8,
                "rationale": "cheap ranged damage",
                "tags": [],
            },
            smg,
        ),
        _decision(
            2,
            2,
            {
                "action": "buy",
                "option_index": 0,
                "confidence": 0.6,
                "rationale": "armor",
                "tags": [],
            },
            bag,
        ),
        _decision(3, 2, {"action": "reroll", "confidence": 0.5, "rationale": "x", "tags": []}, bag),
        _decision(4, 2, None, bag, source="fallback"),
        _decision(
            1,
            1,
            {
                "action": "buy",
                "option_index": 0,
                "confidence": 0.9,
                "rationale": "other run",
                "tags": [],
            },
            bag,
            run_id="other-run",
        ),
    ]
    for r in rows:
        experience.append(decisions, r)

    joined = experience.join_outcomes(decisions, _summary())
    assert len(joined) == 4  # the other run's decision is left out
    assert all(j["run_id"] == RUN_ID for j in joined)
    assert all(j["outcome"] == "death" and j["death_wave"] == 3 for j in joined)

    smg_row, bag_row, reroll_row, fallback_row = joined
    assert smg_row["chosen"] == "weapon_smg_1"
    assert smg_row["confidence"] == 0.8 and smg_row["source"] == "haiku"
    assert smg_row["hp_next_wave"] == 5  # wave 2 ended on 5 HP
    assert smg_row["kept_to_end"] is True  # in the death build
    assert bag_row["chosen"] == "item_bag"
    assert bag_row["hp_next_wave"] == 0  # died in wave 3
    assert bag_row["kept_to_end"] is True
    assert reroll_row["chosen"] == "reroll" and reroll_row["kept_to_end"] is None
    assert fallback_row["chosen"] is None and fallback_row["source"] == "fallback"
    assert fallback_row["confidence"] is None and fallback_row["kept_to_end"] is None
    assert set(smg_row) >= {
        "run_id",
        "kind",
        "character_id",
        "wave",
        "options",
        "chosen",
        "source",
        "confidence",
        "outcome",
        "death_wave",
        "hp_next_wave",
        "kept_to_end",
    }


def test_join_outcomes_kept_to_end_false_when_sold_and_none_without_build(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "item_coupon", "kind": "item", "price": 15, "score": 1.0}]
    experience.append(
        decisions,
        _decision(
            1,
            1,
            {"action": "buy", "option_index": 0, "confidence": 0.8, "rationale": "r", "tags": []},
            opts,
        ),
    )
    summary = _summary()
    assert experience.join_outcomes(decisions, summary)[0]["kept_to_end"] is False

    won = summary.model_copy(update={"outcome": "win", "death": None, "death_wave": None})
    row = experience.join_outcomes(decisions, won)[0]
    assert row["kept_to_end"] is None and row["death_wave"] is None


def test_join_outcomes_counts_a_merged_weapon_as_kept(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "weapon_smg_1", "kind": "weapon", "price": 25, "score": 6.5}]
    experience.append(
        decisions,
        _decision(
            1,
            1,
            {"action": "buy", "option_index": 0, "confidence": 0.8, "rationale": "r", "tags": []},
            opts,
        ),
    )
    summary = _summary()
    summary.death.weapons = ["weapon_smg_2"]  # two tier-1 SMGs combined
    assert experience.join_outcomes(decisions, summary)[0]["kept_to_end"] is True


def test_join_outcomes_reads_build_from_run_jsonl(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0}]
    experience.append(
        decisions,
        _decision(
            1,
            1,
            {"action": "buy", "option_index": 0, "confidence": 0.8, "rationale": "r", "tags": []},
            opts,
        ),
    )
    run = tmp_path / "run.jsonl"
    lines = [
        {"kind": "header", "run_id": RUN_ID, "t": 0},
        {"kind": "snapshot", "t": 1, "build": {"weapons": [], "items": ["item_bag"]}},
        {"kind": "end", "outcome": "won", "wave": 20, "t": 2},
    ]
    run.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    won = _summary().model_copy(update={"outcome": "win", "death": None, "death_wave": None})
    row = experience.join_outcomes(decisions, won, run_jsonl=run)[0]
    assert row["kept_to_end"] is True


def test_append_after_a_truncated_line_starts_a_new_line(tmp_path):
    log = tmp_path / "experience.jsonl"
    experience.append(log, {"character_id": "c", "kind": "shop", "wave": 1})
    with log.open("ab") as fh:
        fh.write(b'{"character_id": "c", "kind": "sh')  # crash mid-write
    experience.append(log, {"character_id": "c", "kind": "shop", "wave": 2})
    assert [r["wave"] for r in experience.query(log, "c", "shop")] == [1, 2]
    assert log.read_bytes().endswith(b"\n")
    assert log.read_bytes().count(b"\n") == 3


def _resp(action, index=None):
    r = {"action": action, "confidence": 0.7, "rationale": "r", "tags": []}
    return r if index is None else {**r, "option_index": index}


@pytest.mark.parametrize("action", ["take", "recycle"])
@pytest.mark.parametrize("source", ["haiku", "rule", "timeout", None])
def test_crate_experience_joins_applied_action_to_sole_item(tmp_path, action, source):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "item_bag", "kind": "item", "score": 2.0}]
    rec = {**_decision(1, 1, _resp(action), opts), "kind": "crate", "screen": "crate"}
    experience.append(decisions, rec)
    run = tmp_path / "run.jsonl"
    if source is not None:
        experience.append(
            run,
            {
                "kind": "crate",
                "id": rec["id"],
                "item_id": "item_bag",
                "action": action,
                "source": source,
            },
        )
    row = experience.join_outcomes(decisions, _summary(), run_jsonl=run)[0]
    expected = None if source is None else source == "haiku"
    assert row["applied"] is expected
    assert row["chosen"] == ("item_bag" if expected is not False else None)
    assert row["kept_to_end"] is (True if expected is not False and action == "take" else None)
    assert row["hp_next_wave"] == 5
    experience.append(tmp_path / "experience.jsonl", row)
    assert experience.query(tmp_path / "experience.jsonl", rec["character_id"], "crate") == [row]


def test_crate_experience_rejects_an_action_mismatch(tmp_path):
    decisions, run = tmp_path / "decisions.jsonl", tmp_path / "run.jsonl"
    rec = {**_decision(1, 1, _resp("take"), [{"id": "item_bag"}]), "kind": "crate"}
    experience.append(decisions, rec)
    experience.append(
        run, {"kind": "crate", "id": rec["id"], "action": "recycle", "source": "haiku"}
    )
    row = experience.join_outcomes(decisions, _summary(), run_jsonl=run)[0]
    assert row["applied"] is False and row["chosen"] is None and row["kept_to_end"] is None


@pytest.mark.parametrize("action", ["take", "recycle"])
def test_reused_crate_events_share_one_applied_decision(tmp_path, action):
    decisions, run = tmp_path / "decisions.jsonl", tmp_path / "run.jsonl"
    rec = {**_decision(1, 1, _resp(action), [{"id": "item_bag"}]), "kind": "crate"}
    experience.append(decisions, rec)
    for _ in range(3):
        experience.append(
            run,
            {
                "kind": "crate",
                "id": rec["id"],
                "item_id": "item_bag",
                "action": action,
                "source": "haiku",
            },
        )
    rows = experience.join_outcomes(decisions, _summary(), run_jsonl=run)
    assert len(rows) == 1
    assert rows[0]["applied"] is True
    assert rows[0]["chosen"] == "item_bag"
    assert rows[0]["kept_to_end"] is (True if action == "take" else None)


@pytest.mark.parametrize("applied", ["pass", "rule", None])
def test_join_outcomes_pass_names_declined_item_without_claiming_ownership(tmp_path, applied):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 3, "id": "item_bag"}]  # use the option index, not its list position
    rec = _decision(1, 1, _resp("pass", 3), opts)
    experience.append(decisions, rec)
    run = tmp_path / "run.jsonl"
    if applied is not None:
        experience.append(run, {"kind": "decision_applied", "id": rec["id"], "applied": applied})
    row = experience.join_outcomes(decisions, _summary(), run_jsonl=run)[0]
    assert row["action"] == "pass"
    assert row["applied"] is (None if applied is None else applied == "pass")
    assert row["chosen"] == (None if applied == "rule" else "item_bag")
    assert row["kept_to_end"] is None  # the fixture holds this item; passing is not buying
    assert row["hp_next_wave"] == 5


def test_join_outcomes_reads_what_the_mod_applied(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0}]
    ups = [{"index": 0, "id": "upgrade_armor_1"}, {"index": 1, "id": "upgrade_range_1"}]
    rows = [
        _decision(1, 1, _resp("buy", 0), opts),  # applied
        _decision(2, 1, _resp("buy", 0), opts),  # the mod fell back to its rules
        {**_decision(3, 1, _resp("pick", 1), ups), "kind": "levelup", "screen": "levelup"},
        {**_decision(4, 2, _resp("pick", 0), ups), "kind": "levelup", "screen": "levelup"},
        {**_decision(5, 2, _resp("revise_plan"), []), "kind": "checkpoint", "screen": "checkpoint"},
        {**_decision(6, 2, _resp("skip"), []), "kind": "checkpoint", "screen": "checkpoint"},
        _decision(7, 2, _resp("buy", 0), opts),  # no matching event in the recording
    ]
    for r in rows:
        experience.append(decisions, r)
    rid = f"{RUN_ID}-00"
    events = [
        {"kind": "header", "run_id": RUN_ID, "t": 0},
        {"kind": "decision_applied", "id": f"{rid}1", "action": "buy", "option_index": 0,
         "applied": "buy"},
        {"kind": "decision_applied", "id": f"{rid}2", "action": "buy", "option_index": 0,
         "applied": "rule"},
        {"kind": "levelup", "id": f"{rid}3", "picked": "upgrade_range_1", "source": "haiku"},
        {"kind": "levelup", "id": f"{rid}4", "picked": "upgrade_range_1", "source": "rule"},
        {"kind": "checkpoint", "id": f"{rid}5", "action": "revise_plan", "applied": "skip",
         "reason": "patch_not_applied"},
        {"kind": "checkpoint", "id": f"{rid}6", "action": "skip", "applied": "skip", "reason": ""},
    ]  # fmt: skip
    run = tmp_path / "run.jsonl"
    run.write_text("".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")
    out = experience.join_outcomes(decisions, _summary(), run_jsonl=run)
    got = [(r["applied"], r["chosen"]) for r in out]
    assert got == [
        (True, "item_bag"),
        (False, None),
        (True, "upgrade_range_1"),
        (False, None),
        (False, None),
        (True, "skip"),
        (None, "item_bag"),
    ]
    assert out[0]["kept_to_end"] is True and out[1]["kept_to_end"] is None
    assert experience.join_outcomes(decisions, _summary())[1]["applied"] is None


def test_join_outcomes_preserves_optional_decline_alongside_buy(tmp_path):
    decisions = tmp_path / "decisions.jsonl"
    opts = [{"index": 0, "id": "item_bag"}, {"index": 1, "id": "item_ghost"}]
    resp = {**_resp("buy", 0), "decline": [1]}
    experience.append(decisions, _decision(1, 1, resp, opts))
    experience.append(decisions, _decision(2, 1, _resp("skip"), opts))
    rows = experience.join_outcomes(decisions, _summary())
    assert rows[0]["decline"] == [1] and rows[0]["chosen"] == "item_bag"
    assert rows[1]["decline"] == []
