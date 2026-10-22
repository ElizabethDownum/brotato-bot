import json
from pathlib import Path

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
