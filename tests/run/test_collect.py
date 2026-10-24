import json
import os
import shutil
from pathlib import Path

import pytest

from brotato_bot import cli
from brotato_bot.report import render
from brotato_bot.run import collect
from brotato_bot.run.models import RunSummary

FIXTURES = Path(__file__).parent / "fixtures"
RUN_ID = "20261022-201500-well_rounded-d0"


@pytest.fixture
def material_events():
    events = collect.parse_jsonl(FIXTURES / "run_telemetry.jsonl")
    events.extend(
        [
            {
                "kind": "wave_end",
                "wave": 1,
                "materials": {
                    "floor_count": 3,
                    "floor_value": 7,
                    "bag_before": 4,
                    "bag_after": 11,
                    "collected_value": 20,
                },
                "trees": {"spawned": 5, "felled": 3, "alive": 2},
            },
            {
                "kind": "wave_end",
                "wave": 2,
                "materials": {
                    "floor_count": 0,
                    "floor_value": 0,
                    "bag_before": 2,
                    "bag_after": 2,
                    "collected_value": 0,
                },
                "trees": {"spawned": 4, "felled": 4, "alive": 0},
            },
        ]
    )
    return events


def test_wave_end_materials_replace_snapshot_estimates(material_events):
    s = collect.summarize(material_events)
    # These recorded values differ from the following snapshot's bag estimate (4).
    md = render.run_report(s)
    assert (
        "| wave | floor count | floor value | bag before | bag after | swept | collected value |"
        in md
    )
    assert "| 1 | 3 | 7 | 4 | 11 | 7 | 20 |" in md
    assert "| 2 | 0 | 0 | 2 | 2 | 0 | 0 |" in md
    assert "| Run total |  |  |  | 2 | 7 | 20 |" in md
    assert "bag swept at wave end" not in md
    assert "bag left at the end of the run" in md
    assert "only through newly spawned pickups" in md
    assert "50 pickups" in md and "unspent value" in md
    # Extensions survive a summary round trip.
    assert render.run_report(render.ReportSummary.model_validate(s.model_dump())) == md


@pytest.mark.parametrize("unknown_waves", [(1,), (1, 2)])
def test_unknown_collected_value_stays_blank(material_events, unknown_waves):
    for event in material_events:
        if event.get("materials") and event["wave"] in unknown_waves:
            event["materials"]["collected_value"] = None
    md = render.run_report(collect.summarize(material_events))
    assert "| 1 | 3 | 7 | 4 | 11 | 7 |  |" in md
    assert "| Run total |  |  |  | 2 | 7 |  |" in md


def test_trees_render_independently_of_materials(material_events):
    for event in material_events:
        event.pop("materials", None)
    md = render.run_report(collect.summarize(material_events))
    assert "## Trees\n\n| wave | spawned | felled | alive |" in md
    assert "| 1 | 5 | 3 | 2 |" in md
    assert "| 2 | 4 | 4 | 0 |" in md
    assert "| Run total |  | 7 |  |" in md


def test_snapshot_value_means_use_only_present_samples(material_events):
    material_events.extend(
        [
            {"kind": "snapshot", "wave": 1, "mats": {"floor_value": 12, "unattached": 0}},
            {"kind": "snapshot", "wave": 1, "mats": {"floor_value": 6, "unattached": 2}},
            {"kind": "snapshot", "wave": 2, "mats": {"floor_value": 0}},
            {"kind": "snapshot", "wave": 2, "mats": {"floor_value": None, "unattached": True}},
        ]
    )
    md = render.run_report(collect.summarize(material_events))
    assert "## Material snapshots" in md
    assert "| mean floor value | mean unattached |" in md
    assert "| 1 | 4 | 6 | 4 | 9 | 1 |" in md
    assert "| 2 | 10 | 10 |  | 0 |  |" in md
    assert "| Run total | 6 | 10 | 4 | 6 | 1 |" in md
    # Older streams can carry these snapshot fields without wave-end telemetry.
    for event in material_events:
        event.pop("materials", None)
    md = render.run_report(collect.summarize(material_events))
    assert "## Materials\n" in md and "## Material snapshots" not in md
    assert "| Run total | 6 | 10 | 4 | 6 | 1 |" in md


def test_absent_wave_telemetry_omits_tables():
    events = collect.parse_jsonl(FIXTURES / "run_small.jsonl")
    events.extend(
        [
            {"kind": "wave_end", "wave": 4, "materials": None, "trees": []},
            {"kind": "wave_end", "materials": {"bag_after": 99}, "trees": {"felled": 99}},
        ]
    )
    md = render.run_report(collect.summarize(events))
    assert "## Materials" not in md and "## Trees" not in md


def test_report_still_accepts_shared_summary_model():
    s = collect.summarize(collect.parse_jsonl(FIXTURES / "run_telemetry.jsonl"))
    assert render.run_report(RunSummary.model_validate(s.model_dump())) == render.run_report(s)


def test_collect_writes_material_and_tree_telemetry(tmp_paths, material_events):
    tmp_paths.runs_in.mkdir(parents=True, exist_ok=True)
    (tmp_paths.runs_in / "materials.jsonl").write_text(
        "\n".join(json.dumps(e) for e in material_events) + "\n", encoding="utf-8"
    )
    md = collect.collect("materials", tmp_paths).read_text(encoding="utf-8")
    assert "| Run total |  |  |  | 2 | 7 | 20 |" in md
    assert "## Trees\n" in md and "| Run total |  | 7 |  |" in md


def test_report_renders_new_telemetry():
    events = collect.parse_jsonl(FIXTURES / "run_telemetry.jsonl")
    plan = {"plan": {"ask_on": ["item_goal"], "item_bonus": {"item_bonus": 3}}}
    s = collect.summarize(events, plan)
    md = render.run_report(s)
    assert "target chal_slow fired on wave 2" in md
    assert "launched by the mod: character_old, weapon_rock, danger 0" in md
    assert "| wave | hp | gold | dmg | kills | speed |" in md
    assert "| 1 | 10 | - | - | - | -21 |" in md
    assert "## Offers" in md and len(s.offers) == 2
    assert "item_goal* 1 20 30; item_bonus* 0 10 7 | item_goal |" in md
    assert s.offers[0].bought == ["item_goal"] and s.offers[1].bought == []
    assert "| 1 | item_beanie | recycle | -16 |" in md
    assert "## Build" in md
    assert "weapon_rock_1 x2" in md and "item_metal_plate x3" in md
    assert "bag swept at wave end" in md
    assert "| 1 | 4 | 6 | 4 |" in md
    assert "| 2 | 10 | 10 |  |" in md
    assert "| Run total | 6 | 10 | 4 |" in md
    assert "sum of swept bag" in md
    assert collect.index_row(s)["target_fired"] is True


def test_target_wave_override_and_first_wave():
    events = [
        {"kind": "challenge", "id": "unknown", "is_target": True},
        {"kind": "wave_end", "wave": 2},
        {"kind": "challenge", "id": "inferred", "is_target": True},
        {"kind": "challenge", "id": "explicit", "is_target": True, "wave": 7},
        {"kind": "challenge", "id": "explicit", "is_target": True, "wave": 4},
    ]
    s = collect.summarize(events)
    assert s.target_waves == {"unknown": 1, "inferred": 3, "explicit": 7}
    assert "| 2 | - | - | - | - |  |" in render.run_report(s)


def test_materials_use_next_wave_peak_and_leave_missing_waves_blank():
    events = collect.parse_jsonl(FIXTURES / "run_telemetry.jsonl")
    # Bag pays out during wave 2, so its final reading must not replace its peak.
    events.extend(
        [
            {"kind": "snapshot", "wave": 2, "mats": {"bag": 9}},
            {"kind": "snapshot", "wave": 2, "mats": {"bag": 0}},
            {"kind": "snapshot", "wave": 2, "mats": {"floor": 2}},
            {"kind": "snapshot", "wave": 4, "mats": {"floor": 8, "bag": 7}},
            {"kind": "snapshot", "wave": 5, "mats": {"floor": 0, "bag": 0}},
        ]
    )
    s = collect.summarize(events)
    assert [(r.wave, r.bag) for r in s.materials] == [(1, 9), (2, None), (4, 0), (5, None)]
    md = render.run_report(s)
    assert "| 1 | 4 | 6 | 9 |" in md
    assert "| 2 | 6 | 10 |  |" in md
    assert "| 4 | 8 | 8 | 0 |" in md
    assert "| 5 | 0 | 0 |  |" in md
    assert "| Run total | 4.66667 | 10 | 9 |" in md


def test_build_on_death_replaces_duplicate_dump():
    s = collect.summarize(
        [
            {"kind": "death", "wave": 2, "build": {"items": ["item_plate"]}},
            {"kind": "build", "items": ["item_plate", "item_plate"]},
            {"kind": "end", "outcome": "death", "wave": 2},
        ]
    )
    md = render.run_report(s)
    assert md.count("item_plate") == 1
    assert "item_plate x2" in md and "Died on wave 2" in md


def test_offer_buys_do_not_leak_between_waves_or_after_go():
    s = collect.summarize(
        [
            {"kind": "offer", "wave": 1, "items": [{"id": "item_goal"}]},
            {"kind": "shop", "wave": 2, "action": "buy", "item_id": "item_goal"},
            {"kind": "shop", "wave": 1, "action": "go"},
            {"kind": "shop", "wave": 1, "action": "buy", "item_id": "item_goal"},
        ]
    )
    assert s.offers[0].bought == []


def test_collect_goal_markers_from_matching_plan_or_saved_proposal(tmp_paths):
    p = tmp_paths
    p.runs_in.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / "run_telemetry.jsonl", p.runs_in / "telemetry.jsonl")
    plan = {"plan_id": "p", "plan": {"ask_on": ["item_goal"]}}
    p.plan_json.write_text(json.dumps(plan), encoding="utf-8")
    md = collect.collect("telemetry", p).read_text(encoding="utf-8")
    assert "item_goal*" in md
    p.plan_json.write_text('{"plan_id":"other"}', encoding="utf-8")
    p.proposals_dir.mkdir(parents=True, exist_ok=True)
    (p.proposals_dir / "saved.md").write_text(
        "## Plan\n```json\n" + json.dumps(plan) + "\n```\n", encoding="utf-8"
    )
    md = collect.collect("telemetry", p).read_text(encoding="utf-8")
    assert "item_goal*" in md


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


def test_older_recording_without_wave_fields():
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
        {"kind": "levelup", "picked": "upgrade_armor_1", "alternatives": [], "source": "rule"},
        {"kind": "warning", "reason": "pause_on_focus_lost is true"},
        {"kind": "bot_state", "state": "idle", "reason": "toggle"},
        {"kind": "end", "outcome": "won", "wave": 20, "hp": 3, "gold": 1},
    ]
    s = collect.summarize(events)
    assert s.outcome == "win"
    assert s.decisions[0].wave == 4 and s.levelups[0].wave == 4
    assert "warning: pause_on_focus_lost is true" in s.notes


def test_checkpoint_uses_own_wave_before_delayed_wave_end():
    s = collect.summarize(
        [
            {"kind": "wave_end", "wave": 9},
            {
                "kind": "decision",
                "request_kind": "checkpoint",
                "wave": 10,
                "id": "cp-10",
                "source": "haiku",
                "response": {"action": "skip"},
            },
            {
                "kind": "checkpoint",
                "wave": 10,
                "id": "cp-10",
                "action": "skip",
                "applied": "skip",
                "reason": "no_patch",
            },
            {"kind": "wave_end", "wave": 10},
        ]
    )
    assert s.checkpoints[0].wave == 10
    assert s.decisions[0].wave == 10
    assert "| 10 | cp-10 | skip | skip | no_patch |" in render.run_report(s)


def test_checkpoint_without_wave_uses_last_wave():
    s = collect.summarize(
        [
            {"kind": "checkpoint", "applied": "skip"},
            {"kind": "wave_end", "wave": 9},
            {"kind": "checkpoint", "applied": "skip", "reason": "no_sidecar"},
        ]
    )
    assert [c.wave for c in s.checkpoints] == [None, 9]
    assert "| 9 | - | - | skip | no_sidecar |" in render.run_report(s)


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
        "target_fired": True,
    }


def test_index_row_target_fired_is_false_without_a_completed_target():
    s = collect.summarize([{"kind": "header", "run_id": "r", "plan_id": "p1"}])
    assert collect.index_row(s)["target_fired"] is False


def test_recollect_refreshes_target_fired(tmp_paths):
    # O7: a row written before target_fired existed gains it on re-collect.
    p = tmp_paths
    _install(p, "run_small.jsonl")
    p.runs_out.mkdir(parents=True)
    old = {"run_id": RUN_ID, "outcome": "death", "target_challenge": "chal_gatherer_1"}
    (p.runs_out / "index.json").write_text(json.dumps([old]), encoding="utf-8")
    collect.collect(RUN_ID, p)
    index = json.loads((p.runs_out / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1
    assert index[0]["target_fired"] is True


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
