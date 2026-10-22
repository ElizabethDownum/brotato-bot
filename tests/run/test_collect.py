import json
import os
import shutil
from pathlib import Path

from brotato_bot import cli
from brotato_bot.report import render
from brotato_bot.run import collect

FIXTURES = Path(__file__).parent / "fixtures"
RUN_ID = "20261022-201500-well_rounded-d0"


def test_collect_summarizes_fixture():
    s = collect.summarize(collect.parse_jsonl(FIXTURES / "run_small.jsonl"))
    assert s.run_id == RUN_ID
    assert s.character_id == "character_well_rounded"
    assert s.danger == 0
    assert s.plan_id == "well-rounded-v1"
    assert s.outcome == "death"
    assert s.death_wave == 3
    assert len(s.shop) == 2
    assert [w.wave for w in s.waves if w.completed] == [1, 2]
    assert (s.waves[0].hp_end, s.waves[0].gold_end, s.waves[0].kills) == (8, 31, 40)
    assert s.waves[-1].wave == 3 and not s.waves[-1].completed
    assert s.waves[-1].damage_taken == 12
    assert s.hp_end_last_wave == 5
    assert [d.source for d in s.decisions] == ["haiku", "haiku"]
    assert s.decisions[0].confidence == 0.8
    assert s.decisions[0].rationale == "cheap ranged damage"
    assert [(r.wave, r.action, r.source) for r in s.shop] == [
        (1, "buy", "haiku"),
        (2, "buy", "haiku"),
    ]
    assert [r.item for r in s.shop] == ["weapon_smg_1", "item_bag"]
    assert s.shop[0].gold_after == 6
    assert "warning: sidecar timeouts; asking disabled for this run" in s.notes
    assert s.levelups[0].wave == 1 and s.levelups[0].id is None
    assert s.levelups[0].picked == "upgrade_ranged_damage_1"
    assert s.levelups[0].source == "rule"
    assert s.challenges == ["chal_gatherer_1"]
    assert s.targets_completed == ["chal_gatherer_1"]
    assert s.death is not None and s.death.killer == "enemy_charger"
    assert s.checkpoints[0].reason == "no_sidecar"


def test_collect_tolerates_truncated_last_line():
    events = collect.parse_jsonl(FIXTURES / "run_truncated.jsonl")
    assert events[-1]["kind"] == "wave_end"
    s = collect.summarize(events)
    assert s.outcome == "incomplete"
    assert s.death_wave is None
    assert [w.wave for w in s.waves] == [1, 2]
    assert "| 2 |" in render.run_report(s)


def test_parse_jsonl_skips_only_a_bad_final_line(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text('{"kind":"header"}\nnot json\n{"kind":"end"}\n', encoding="utf-8")
    try:
        collect.parse_jsonl(f)
    except ValueError as exc:
        assert "line 2" in str(exc)
    else:
        raise AssertionError("a corrupt middle line must not pass silently")


def test_older_recording_without_shop_or_wave_fields():
    rid = "r-001"
    events = [
        {"kind": "header", "run_id": "r", "character_id": "c", "danger": 2, "plan_id": "p"},
        {"kind": "wave_end", "wave": 4, "hp": 10, "gold": 30, "damage_taken": 1, "kills": 9},
        {
            "kind": "decision",
            "request_kind": "shop",
            "id": rid,
            "source": "haiku",
            "response": {"action": "buy", "option_index": 1, "confidence": 0.7},
        },
        {
            "kind": "decision_applied",
            "id": rid,
            "action": "buy",
            "option_index": 1,
            "applied": "buy",
        },
        {"kind": "levelup", "picked": "upgrade_armor_1", "alternatives": [], "source": "rule"},
        {"kind": "warning", "reason": "pause_on_focus_lost is true"},
        {"kind": "bot_state", "state": "idle", "reason": "toggle"},
        {"kind": "end", "outcome": "won", "wave": 20, "hp": 3, "gold": 1},
    ]
    requests = {
        rid: {
            "options": [
                {"index": 0, "id": "item_bag", "price": 20, "score": 2.0},
                {"index": 1, "id": "weapon_smg_1", "price": 25, "score": 6.5},
            ]
        }
    }
    s = collect.summarize(events, requests)
    assert s.outcome == "win"
    assert [(r.wave, r.action, r.item, r.price, r.score, r.source) for r in s.shop] == [
        (4, "buy", "weapon_smg_1", 25, 6.5, "haiku")
    ]
    assert s.decisions[0].wave == 4 and s.levelups[0].wave == 4
    assert "warning: pause_on_focus_lost is true" in s.notes


def test_end_outcome_mapping():
    header = {"kind": "header", "run_id": "r", "character_id": "c", "danger": 1, "plan_id": "p"}
    for end, want in [
        ("won", "win"),
        ("death", "death"),
        ("abandoned", "incomplete"),
        ("quit", "incomplete"),
    ]:
        s = collect.summarize([header, {"kind": "end", "outcome": end, "wave": 20}])
        assert s.outcome == want, end
    assert collect.summarize([header]).outcome == "incomplete"


def test_report_contains_wave_table_and_death():
    s = collect.summarize(collect.parse_jsonl(FIXTURES / "run_small.jsonl"))
    md = render.run_report(s)
    assert md.startswith(f"# Run {RUN_ID}")
    assert "| 3 |" in md
    assert "Died on wave 3" in md
    assert "enemy_charger" in md
    headings = [line for line in md.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Plan and target",
        "## Waves",
        "## Shop",
        "## Level-ups",
        "## Decisions",
        "## Death",
        "## Challenges",
    ]


def _install(tmp_paths, name, run_id=RUN_ID):
    tmp_paths.runs_in.mkdir(parents=True, exist_ok=True)
    dst = tmp_paths.runs_in / f"{run_id}.jsonl"
    shutil.copyfile(FIXTURES / name, dst)
    return dst


def test_collect_writes_report_copy_and_index_row(tmp_paths):
    p = tmp_paths
    _install(p, "run_small.jsonl")
    p.plan_json.write_text(
        json.dumps(
            {
                "plan_id": "well-rounded-v1",
                "character_id": "character_well_rounded",
                "target_challenge": "",
                "plan": {},
            }
        ),
        encoding="utf-8",
    )
    p.config_json.write_text(json.dumps({"target_challenge": "chal_gatherer_1"}), encoding="utf-8")
    p.requests_dir.mkdir(parents=True)
    (p.requests_dir / f"{RUN_ID}-001.json").write_text(
        json.dumps(
            {
                "id": f"{RUN_ID}-001",
                "kind": "shop",
                "options": [
                    {"index": 0, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0},
                    {"index": 1, "id": "weapon_smg_1", "kind": "weapon", "price": 25, "score": 6.5},
                ],
            }
        ),
        encoding="utf-8",
    )
    p.runs_out.mkdir(parents=True)
    other = {"run_id": "older", "outcome": "win"}
    (p.runs_out / "index.json").write_text(json.dumps([other]), encoding="utf-8")

    out = collect.collect(RUN_ID, p)

    assert out == p.runs_out / f"{RUN_ID}.md"
    md = out.read_text(encoding="utf-8")
    assert "| 1 | buy | weapon_smg_1 | 25 | 6.5 | haiku |" in md
    assert "chal_gatherer_1" in md
    assert (p.runs_out / f"{RUN_ID}.jsonl").read_bytes() == (
        FIXTURES / "run_small.jsonl"
    ).read_bytes()
    index = json.loads((p.runs_out / "index.json").read_text(encoding="utf-8"))
    assert index[0] == other
    assert index[1] == {
        "run_id": RUN_ID,
        "character_id": "character_well_rounded",
        "danger": 0,
        "plan_id": "well-rounded-v1",
        "target_challenge": "chal_gatherer_1",
        "outcome": "death",
        "death_wave": 3,
        "hp_end_last_wave": 5,
        "proposal_n": None,
    }


def test_collect_twice_keeps_one_row_and_creates_index(tmp_paths):
    _install(tmp_paths, "run_truncated.jsonl")
    collect.collect(RUN_ID, tmp_paths)
    collect.collect(RUN_ID, tmp_paths)
    index = json.loads((tmp_paths.runs_out / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1
    assert index[0]["outcome"] == "incomplete"
    assert index[0]["target_challenge"] == "chal_gatherer_1"  # the is_target challenge line


def test_resolve_target_falls_back_to_plan_then_config(tmp_paths):
    p = tmp_paths
    s = collect.summarize([{"kind": "header", "run_id": "r", "plan_id": "p1"}])
    assert collect.resolve_target(s, p) is None
    p.config_json.parent.mkdir(parents=True, exist_ok=True)
    p.config_json.write_text(json.dumps({"target_challenge": "chal_cfg"}), encoding="utf-8")
    assert collect.resolve_target(s, p) == "chal_cfg"
    p.plan_json.write_text(
        json.dumps({"plan_id": "other", "target_challenge": "chal_x"}), encoding="utf-8"
    )
    assert collect.resolve_target(s, p) == "chal_cfg"
    p.plan_json.write_text(
        json.dumps({"plan_id": "p1", "target_challenge": "chal_plan"}), encoding="utf-8"
    )
    assert collect.resolve_target(s, p) == "chal_plan"


def test_collect_cli_latest(tmp_paths, capsys):
    old = _install(tmp_paths, "run_truncated.jsonl", run_id="20261021-100000-well_rounded-d0")
    os.utime(old, (1_000_000, 1_000_000))
    _install(tmp_paths, "run_small.jsonl")
    assert cli.main(["collect", "--latest"]) == 0
    assert (tmp_paths.runs_out / f"{RUN_ID}.md").is_file()
    assert not (tmp_paths.runs_out / "20261021-100000-well_rounded-d0.md").exists()


def test_collect_cli_missing_run(tmp_paths, capsys):
    assert cli.main(["collect", "nope"]) == 1
