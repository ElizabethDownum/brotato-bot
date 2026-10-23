import json
from datetime import date
from pathlib import Path

from brotato_bot import cli
from brotato_bot.run import stagnation

TARGET = "chal_a"


def row(run_id, death=14, outcome="death", plan="well-rounded-v1", target=TARGET):
    return {
        "run_id": run_id,
        "character_id": "character_well_rounded",
        "danger": 0,
        "plan_id": plan,
        "target_challenge": target,
        "outcome": outcome,
        "death_wave": death,
        "hp_end_last_wave": 10,
        "proposal_n": None,
        "profile_id": 0,
    }


def test_no_runs_is_fresh():
    v = stagnation.verdict([], TARGET)
    assert v.state == "fresh"
    assert v.runs_considered == []


def test_incomplete_and_other_target_rows_are_ignored():
    rows = [
        row("r1", 14),
        row("r2", 13, outcome="incomplete"),
        row("r3", 14, target="chal_b"),
        row("r4", 14),
    ]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "fresh"


def test_improving_death_wave_is_progressing():
    rows = [row("r1", 9), row("r2", 12), row("r3", 14)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "progressing"
    assert v.runs_considered == ["r1", "r2", "r3"]


def test_three_flat_deaths_is_stagnant():
    rows = [row("r1", 14), row("r2", 13), row("r3", 14)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "stagnant"
    assert "14, 13, 14" in v.reason
    assert v.runs_considered == ["r1", "r2", "r3"]


def test_win_resets():
    rows = [row("r1", 14), row("r2", 13), row("r3", 15, outcome="win")]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "progressing"


def test_escalate_after_two_stagnant_with_changes():
    deaths = [14, 13, 14, 14, 13, 14]
    plans = ["well-rounded-v1"] * 3 + ["gatherer-v1"] * 3
    rows = [row(f"r{i + 1}", d, plan=p) for i, (d, p) in enumerate(zip(deaths, plans))]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "escalate"
    assert "plan well-rounded -> gatherer" in v.reason
    assert v.runs_considered == ["r4", "r5", "r6"]


def test_plan_version_bump_is_not_a_change():
    deaths = [14, 13, 14, 14, 13, 14]
    plans = ["well-rounded-v1"] * 3 + ["well-rounded-v2"] * 3
    rows = [row(f"r{i + 1}", d, plan=p) for i, (d, p) in enumerate(zip(deaths, plans))]
    assert stagnation.verdict(rows, TARGET).state == "stagnant"


def test_mark_paused_appends_line(tmp_path):
    targets = tmp_path / "targets.md"
    targets.write_text("# Targets\n", encoding="utf-8")
    proposal = Path("proposals") / "p1.md"

    stagnation.mark_paused(targets, TARGET, proposal, date(2026, 10, 22))

    assert targets.read_text(encoding="utf-8") == (
        f"# Targets\npaused: {TARGET} since 2026-10-22, evidence in {proposal}\n"
    )


def test_cli_defaults_to_newest_target_and_marks_paused(tmp_paths, capsys):
    p = tmp_paths
    p.runs_out.mkdir(parents=True, exist_ok=True)
    rows = [row("r1", 14), row("r2", 13), row("r3", 14), row("r4", 9, target="chal_b")]
    (p.runs_out / "index.json").write_text(json.dumps(rows), encoding="utf-8")

    assert cli.main(["stagnation"]) == 0
    assert capsys.readouterr().out.strip() == "fresh: 1 finished run(s) on chal_b; need 3"

    assert cli.main(["stagnation", "--target", TARGET]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0].startswith("stagnant: ")
    assert out[0].endswith("[runs: r1, r2, r3]")

    assert cli.main(["stagnation", "--target", TARGET, "--mark-paused", "proposals/p1.md"]) == 0
    capsys.readouterr()
    text = (p.project_root / "targets.md").read_text(encoding="utf-8")
    assert text.endswith(
        f"paused: {TARGET} since {date.today().isoformat()}, evidence in {Path('proposals/p1.md')}\n"
    )
