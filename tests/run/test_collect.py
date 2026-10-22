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


def _install_decision(paths):
    paths.decisions_dir.mkdir(parents=True, exist_ok=True)
    decision = {
        "id": f"{RUN_ID}-001",
        "run_id": RUN_ID,
        "kind": "shop",
        "character_id": "character_well_rounded",
        "wave": 1,
        "options": [{"index": 1, "id": "weapon_smg_1"}],
        "decision": {"action": "buy", "option_index": 1, "confidence": 0.8},
        "source": "haiku",
    }
    (paths.decisions_dir / f"{RUN_ID}.jsonl").write_text(
        json.dumps({**decision, "run_id": "another-run", "id": "another-id"})
        + "\n"
        + json.dumps(decision)
        + "\n",
        encoding="utf-8",
    )


def test_collect_appends_experience(tmp_paths):
    _install(tmp_paths, "run_small.jsonl")
    _install_decision(tmp_paths)

    report = collect.collect(RUN_ID, tmp_paths)

    records = collect.parse_jsonl(tmp_paths.decisions_dir / "experience.jsonl")
    assert len(records) == 1
    assert records[0]["death_wave"] == 3
    assert records[0]["id"] == f"{RUN_ID}-001"
    assert records[0]["run_id"] == RUN_ID
    assert records[0]["outcome"] == "death"
    assert records[0]["chosen"] == "weapon_smg_1"
    assert records[0]["kept_to_end"] is True
    md = report.read_text(encoding="utf-8")
    assert "| kind | action | source | confidence | rationale | outcome |" in md
    assert "| shop | buy | haiku | 0.8 | cheap ranged damage | death |" in md
    assert "| shop | buy | haiku | 0.6 | armor for wave 3 |  |" in md


def test_collect_twice_does_not_duplicate_experience(tmp_paths):
    _install(tmp_paths, "run_small.jsonl")
    _install_decision(tmp_paths)
    # A matching decision id in another run must not suppress this run's record.
    log = tmp_paths.decisions_dir / "experience.jsonl"
    log.write_text(json.dumps({"run_id": "older", "id": f"{RUN_ID}-001"}) + "\n", encoding="utf-8")
    collect.collect(RUN_ID, tmp_paths)
    before = log.read_bytes()
    report = collect.collect(RUN_ID, tmp_paths)
    assert log.read_bytes() == before
    assert len(collect.parse_jsonl(log)) == 2
    assert "| cheap ranged damage | death |" in report.read_text(encoding="utf-8")


def test_collect_keeps_every_decision_without_an_id(tmp_paths):
    _install(tmp_paths, "run_small.jsonl")
    _install_decision(tmp_paths)
    decisions = tmp_paths.decisions_dir / f"{RUN_ID}.jsonl"
    unlabelled = {"run_id": RUN_ID, "kind": "shop", "decision": {"action": "reroll"}}
    decisions.write_text(
        json.dumps(unlabelled) + "\n" + json.dumps(unlabelled) + "\n", encoding="utf-8"
    )
    log = tmp_paths.decisions_dir / "experience.jsonl"
    collect.collect(RUN_ID, tmp_paths)
    ids = [r["id"] for r in collect.parse_jsonl(log)]
    assert ids == [f"{RUN_ID}-line000", f"{RUN_ID}-line001"]
    collect.collect(RUN_ID, tmp_paths)
    assert len(collect.parse_jsonl(log)) == 2


def test_collect_missing_decisions_leaves_experience_absent(tmp_paths):
    _install(tmp_paths, "run_small.jsonl")
    report = collect.collect(RUN_ID, tmp_paths)
    assert not (tmp_paths.decisions_dir / "experience.jsonl").exists()
    md = report.read_text(encoding="utf-8")
    assert "| kind | action | source | confidence | rationale | outcome |" in md
    assert "| cheap ranged damage |  |" in md


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
        "profile_id": 1,
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


def test_collect_rejects_traversal_run_id(tmp_paths, tmp_path):
    import pytest

    _install(tmp_paths, "run_small.jsonl")
    outside = tmp_path / "outside.jsonl"
    shutil.copyfile(FIXTURES / "run_small.jsonl", outside)
    before = sorted(tmp_path.rglob("*"))
    for bad in (r"..\..\outside", "../../outside", str(tmp_path / "outside"), "..", ""):
        with pytest.raises(ValueError):
            collect.collect(bad, tmp_paths)
        assert cli.main(["collect", bad]) == 1
    assert sorted(tmp_path.rglob("*")) == before


def test_request_lookup_skips_non_plain_decision_id(tmp_paths):
    p = tmp_paths
    secret = p.requests_dir.parent.parent / "settings.json"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(
        json.dumps({"options": [{"index": 0, "id": "LEAKED", "price": 1}]}), encoding="utf-8"
    )
    bad_id = r"..\..\settings"
    lines = [
        {"kind": "header", "run_id": "r1", "character_id": "c", "danger": 0, "plan_id": "p"},
        {"kind": "wave_end", "wave": 1, "hp": 5, "gold": 9, "damage_taken": 0, "kills": 3},
        {
            "kind": "decision",
            "request_kind": "shop",
            "id": bad_id,
            "source": "haiku",
            "response": {"action": "buy", "option_index": 0, "confidence": 0.5},
        },
        {
            "kind": "decision_applied",
            "id": bad_id,
            "action": "buy",
            "option_index": 0,
            "applied": "buy",
        },
        {"kind": "end", "outcome": "quit"},
    ]
    p.runs_in.mkdir(parents=True, exist_ok=True)
    (p.runs_in / "r1.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )
    p.requests_dir.mkdir(parents=True, exist_ok=True)
    md = collect.collect("r1", p).read_text(encoding="utf-8")
    assert "LEAKED" not in md
    assert "| 1 | buy | - | - | - | haiku |" in md


def test_index_run_id_is_the_file_name_and_mismatch_is_noted(tmp_paths):
    _install(tmp_paths, "run_small.jsonl", run_id="renamed-run")
    md = collect.collect("renamed-run", tmp_paths).read_text(encoding="utf-8")
    assert md.startswith("# Run renamed-run")
    assert "differs from the file name" in md
    index = json.loads((tmp_paths.runs_out / "index.json").read_text(encoding="utf-8"))
    assert index[0]["run_id"] == "renamed-run"


def test_latest_breaks_mtime_ties_by_name(tmp_paths):
    a = _install(tmp_paths, "run_small.jsonl", run_id="20261022-000000-a-d0")
    b = _install(tmp_paths, "run_small.jsonl", run_id="20261022-000001-a-d0")
    for f in (b, a):
        os.utime(f, (2_000_000, 2_000_000))
    assert collect.latest_run_id(tmp_paths) == "20261022-000001-a-d0"


def _install_on_profile(tmp_paths, profile_id):
    dst = _install(tmp_paths, "run_small.jsonl")
    text = dst.read_text(encoding="utf-8")
    dst.write_text(text.replace('"profile_id":1,', f'"profile_id":{profile_id},', 1), "utf-8")


def test_collect_records_experience_only_for_the_bot_profile(tmp_paths):
    _install_on_profile(tmp_paths, 0)
    _install_decision(tmp_paths)
    report = collect.collect(RUN_ID, tmp_paths)
    assert not (tmp_paths.decisions_dir / "experience.jsonl").exists()
    assert "profile 0 is not the bot profile (1)" in report.read_text(encoding="utf-8")
    index = json.loads((tmp_paths.runs_out / "index.json").read_text(encoding="utf-8"))
    assert index[0]["profile_id"] == 0

    tmp_paths.config_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_paths.config_json.write_text(json.dumps({"bot_profile_id": 2}), encoding="utf-8")
    _install_on_profile(tmp_paths, 2)
    collect.collect(RUN_ID, tmp_paths)
    assert len(collect.parse_jsonl(tmp_paths.decisions_dir / "experience.jsonl")) == 1


def test_collect_records_no_experience_for_a_run_in_progress(tmp_paths):
    _install(tmp_paths, "run_truncated.jsonl")
    _install_decision(tmp_paths)
    report = collect.collect(RUN_ID, tmp_paths)
    assert report.is_file()
    assert json.loads((tmp_paths.runs_out / "index.json").read_text("utf-8"))[0]["outcome"] == (
        "incomplete"
    )
    assert not (tmp_paths.decisions_dir / "experience.jsonl").exists()
