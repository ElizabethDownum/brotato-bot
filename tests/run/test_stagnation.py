import json
from datetime import date
from pathlib import Path

from brotato_bot import cli
from brotato_bot.run import stagnation

TARGET = "chal_a"


def row(
    run_id,
    death=14,
    outcome="death",
    plan="well-rounded-v1",
    target=TARGET,
    hp=10,
    profile=1,
    character="character_well_rounded",
    fired=False,
):
    return {
        "run_id": run_id,
        "character_id": character,
        "danger": 0,
        "plan_id": plan,
        "target_challenge": target,
        "outcome": outcome,
        "death_wave": death,
        "hp_end_last_wave": hp,
        "proposal_n": None,
        "profile_id": profile,
        "target_fired": fired,
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
    assert "deaths" not in v.reason
    assert v.runs_considered == ["r1", "r2", "r3"]


def test_win_without_the_target_firing_is_not_progress():
    # Run 1 (2026-10-22) won on chal_slow without lowering speed: a win that misses the
    # target must count toward stagnant, and a win's end wave never beats a death.
    rows = [row("r1", 14), row("r2", 13), row("r3", 20, hp=60, outcome="win")]
    assert stagnation.verdict(rows, TARGET).state == "stagnant"
    wins = [row(f"r{i}", 20, hp=h, outcome="win") for i, h in enumerate((60, 70, 88), 1)]
    assert stagnation.verdict(wins, TARGET).state == "stagnant"


def test_win_in_the_first_slot_is_not_beaten_by_a_later_death():
    rows = [row("r1", None, outcome="win"), row("r2", 3), row("r3", 3)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "stagnant"
    assert "win, 3, 3" in v.reason and "deaths" not in v.reason


def test_win_first_window_escalates_after_a_family_change():
    rows = [row("r1", None, outcome="win"), row("r2", 3), row("r3", 3)]
    rows += [row(f"r{i}", 3, plan="gatherer-v1") for i in (4, 5, 6)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "escalate"
    assert "plan well-rounded -> gatherer at run r4" in v.reason
    assert "runs r1, r2, r3 before it ended at waves win, 3, 3" in v.reason


def test_win_that_fired_the_target_is_progress():
    rows = [row("r1", 14), row("r2", 13), row("r3", 20, outcome="win", fired=True)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "progressing" and v.reason == "the target fired in run r3"


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


def test_regression_with_more_hp_is_not_progress():
    # O3: dying earlier with more HP is worse, not better.
    rows = [row("r1", 14, hp=5), row("r2", 9, hp=30), row("r3", 9, hp=30)]
    assert stagnation.verdict(rows, TARGET).state == "stagnant"


def test_same_wave_more_hp_is_progress():
    rows = [row("r1", 14, hp=5), row("r2", 14, hp=6), row("r3", 13, hp=30)]
    assert stagnation.verdict(rows, TARGET).state == "progressing"


def test_missing_wave_and_hp_read_as_zero():
    rows = [row("r1", None, hp=None), row("r2", None, hp=None), row("r3", 1, hp=None)]
    assert stagnation.verdict(rows, TARGET).state == "progressing"


def test_escalate_needs_the_runs_since_the_change_to_be_stagnant():
    # O4: A flat, then B improved (12, 14, 16) and plateaued (16, 16, 16): stagnant, not escalate.
    deaths = [10, 10, 10, 12, 14, 16, 16, 16, 16]
    plans = ["a-v1"] * 3 + ["b-v1"] * 6
    rows = [row(f"r{i + 1}", d, plan=p) for i, (d, p) in enumerate(zip(deaths, plans))]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "stagnant"
    assert "16, 16, 16" in v.reason


def test_escalate_reason_names_the_compared_runs():
    deaths = [10, 10, 10, 11, 11, 11, 10]
    plans = ["a-v1"] * 3 + ["b-v1"] * 4
    rows = [row(f"r{i + 1}", d, plan=p) for i, (d, p) in enumerate(zip(deaths, plans))]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "escalate"
    assert "plan a -> b at run r4" in v.reason
    assert "runs r4, r5, r6, r7 ended at waves 11, 11, 11, 10" in v.reason
    assert "runs r1, r2, r3 before it ended at waves 10, 10, 10" in v.reason
    assert v.runs_considered == ["r5", "r6", "r7"]


def test_character_change_counts_for_escalate():
    deaths = [14, 13, 14, 14, 13, 14]
    chars = ["character_a"] * 3 + ["character_b"] * 3
    rows = [row(f"r{i + 1}", d, character=c) for i, (d, c) in enumerate(zip(deaths, chars))]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "escalate"
    assert "character character_a -> character_b" in v.reason


def test_owner_profile_rows_are_ignored():
    # O2: a profile-0 run in the middle does not count; a row without profile_id does.
    rows = [row("r1", 10), row("m1", 30, profile=0), row("r2", 9), row("r3", 10)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "stagnant"
    assert v.runs_considered == ["r1", "r2", "r3"]
    old = row("r0", 10)
    del old["profile_id"]
    v = stagnation.verdict([old, row("r2", 9), row("r3", 10)], TARGET)
    assert v.state == "stagnant"
    assert v.runs_considered == ["r0", "r2", "r3"]


def test_target_fired_counts_as_progress():
    # O7: a death that fired the target is progress, like a win.
    rows = [row("r1", 14), row("r2", 13), row("r3", 14, fired=True)]
    v = stagnation.verdict(rows, TARGET)
    assert v.state == "progressing"
    assert v.reason == "the target fired in run r3"
    no_key = [row("r1", 14), row("r2", 13), row("r3", 14)]
    del no_key[2]["target_fired"]
    assert stagnation.verdict(no_key, TARGET).state == "stagnant"


def test_target_fired_before_the_change_blocks_escalate():
    deaths = [14, 13, 14, 14, 13, 14]
    plans = ["well-rounded-v1"] * 3 + ["gatherer-v1"] * 3
    rows = [row(f"r{i + 1}", d, plan=p) for i, (d, p) in enumerate(zip(deaths, plans))]
    rows[1]["target_fired"] = True
    assert stagnation.verdict(rows, TARGET).state == "stagnant"


def test_mark_paused_appends_line(tmp_path):
    targets = tmp_path / "targets.md"
    targets.write_text("# Targets\n", encoding="utf-8")
    proposal = Path("proposals") / "p1.md"

    assert stagnation.mark_paused(targets, TARGET, proposal, date(2026, 10, 22)) is True

    assert targets.read_text(encoding="utf-8") == (
        f"# Targets\npaused: {TARGET} since 2026-10-22, evidence in {proposal}\n"
    )


def test_mark_paused_is_idempotent(tmp_path):
    # O11: a second pause of the same target writes nothing; another target still appends.
    targets = tmp_path / "targets.md"
    targets.write_text(
        f"# Targets\npaused: {TARGET} since 2026-10-01, evidence in x.md\n", encoding="utf-8"
    )
    before = targets.read_text(encoding="utf-8")
    assert stagnation.mark_paused(targets, TARGET, Path("p2.md"), date(2026, 10, 22)) is False
    assert targets.read_text(encoding="utf-8") == before
    assert stagnation.mark_paused(targets, "chal_a2", Path("p2.md"), date(2026, 10, 22)) is True
    assert targets.read_text(encoding="utf-8").endswith(
        "paused: chal_a2 since 2026-10-22, evidence in p2.md\n"
    )


ESCALATE_DEATHS = [14, 13, 14, 14, 13, 14]
ESCALATE_PLANS = ["well-rounded-v1"] * 3 + ["gatherer-v1"] * 3


def _write_index(p, rows):
    p.runs_out.mkdir(parents=True, exist_ok=True)
    (p.runs_out / "index.json").write_text(json.dumps(rows), encoding="utf-8")


def test_cli_defaults_to_newest_target_and_marks_paused(tmp_paths, capsys):
    p = tmp_paths
    rows = [
        row(f"r{i + 1}", d, plan=pl)
        for i, (d, pl) in enumerate(zip(ESCALATE_DEATHS, ESCALATE_PLANS))
    ]
    _write_index(p, rows + [row("r7", 9, target="chal_b")])

    assert cli.main(["stagnation"]) == 0
    assert capsys.readouterr().out.strip() == "fresh (chal_b): 1 finished run(s) on chal_b; need 3"

    assert cli.main(["stagnation", "--target", TARGET]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0].startswith(f"escalate ({TARGET}): ")
    assert out[0].endswith("[runs: r4, r5, r6]")

    assert cli.main(["stagnation", "--target", TARGET, "--mark-paused", "proposals/p1.md"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith(f"paused: {TARGET} recorded")
    text = (p.project_root / "targets.md").read_text(encoding="utf-8")
    assert text.endswith(
        f"paused: {TARGET} since {date.today().isoformat()}, evidence in {Path('proposals/p1.md')}\n"
    )

    assert cli.main(["stagnation", "--target", TARGET, "--mark-paused", "proposals/p2.md"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == f"already paused: {TARGET}"
    assert (p.project_root / "targets.md").read_text(encoding="utf-8") == text


def test_cli_default_target_skips_owner_rows(tmp_paths, capsys):
    _write_index(tmp_paths, [row("r1", 14), row("m1", 9, target="chal_mine", profile=0)])
    assert cli.main(["stagnation"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == f"fresh ({TARGET}): 1 finished run(s) on {TARGET}; need 3"


def test_cli_mark_paused_refused_unless_escalate(tmp_paths, capsys):
    p = tmp_paths
    _write_index(p, [row("r1", 14), row("r2", 13), row("r3", 14)])

    assert cli.main(["stagnation", "--target", TARGET, "--mark-paused", "proposals/p1.md"]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith(f"stagnant ({TARGET}): ")
    assert out[1] == "stagnation: --mark-paused refused: verdict is stagnant, not escalate"
    assert not (p.project_root / "targets.md").exists()


def test_cli_empty_index_is_fresh(tmp_paths, capsys):
    assert cli.main(["stagnation"]) == 0
    assert capsys.readouterr().out.strip() == "fresh: no runs on any target"
