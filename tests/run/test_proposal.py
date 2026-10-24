import io
import json
import re
import sys
from datetime import date
from pathlib import Path

from brotato_bot import cli
from brotato_bot.run import proposal

REPO = Path(__file__).resolve().parents[2]
TARGET = "chal_gatherer_1"
CHARACTER = "character_well_rounded"


def _state(**overrides):
    """An unlock state where TARGET is open and CHARACTER is unlocked."""
    state = {
        "characters": {CHARACTER: {"unlocked": True, "unlocked_by": None}},
        "done": [],
        "open": [TARGET],
        "blocked": [],
        "progress": {TARGET: {"requires_character": None, "stat": "", "number": 0, "value": 5}},
    }
    state.update(overrides)
    return state


UNLOCKED = _state()
LOCKED = _state(characters={CHARACTER: {"unlocked": False, "unlocked_by": "chal_x"}})


def test_next_proposal_number_increments(tmp_path):
    assert proposal.next_path(tmp_path, date(2026, 10, 22)) == tmp_path / "2026-10-22-001.md"
    (tmp_path / "2026-10-21-002.md").write_text("x", encoding="utf-8")
    (tmp_path / "2026-10-20-007.md").write_text("x", encoding="utf-8")
    (tmp_path / "TEMPLATE.md").write_text("x", encoding="utf-8")
    assert proposal.next_path(tmp_path, date(2026, 10, 22)) == tmp_path / "2026-10-22-008.md"


def test_extract_plan_reads_fenced_json(proposal_md):
    plan = proposal.extract_plan(proposal_md())
    assert plan == {
        "plan_id": "well-rounded-v1",
        "character_id": CHARACTER,
        "plan": {"weapon_type": "ranged"},
    }


def test_extract_plan_rejects_two_json_blocks(proposal_md):
    text = proposal_md().replace("## Why", '```json\n{"x": 1}\n```\n\n## Why')
    errors = proposal.validate(text, UNLOCKED)
    assert "## Plan: needs exactly one ```json block, found 2" in errors


def test_next_run_parses_the_four_bullets(proposal_md):
    assert proposal.next_run(proposal_md()) == {
        "character_id": CHARACTER,
        "danger": 0,
        "target": TARGET,
        "starting_weapon": "any",
    }
    assert proposal.next_run(proposal_md(starting_weapon="weapon_rock"))["starting_weapon"] == (
        "weapon_rock"
    )
    none = proposal_md().replace(f"- target: {TARGET}", "- target: none")
    assert proposal.next_run(none)["target"] is None


def test_next_run_rejects_duplicate_bullet(proposal_md):
    text = proposal_md().replace("- danger: 0", "- danger: 0\n- danger: 1")
    errors = proposal.validate(text, UNLOCKED)
    assert any("needs the bullets" in e for e in errors)


def test_next_run_rejects_extra_bullet(proposal_md):
    text = proposal_md().replace(f"- target: {TARGET}", f"- target: {TARGET}\n- note: anything")
    errors = proposal.validate(text, UNLOCKED)
    assert any("not a character, danger, target or starting_weapon bullet" in e for e in errors)


def test_next_run_rejects_unknown_bullet_text(proposal_md):
    text = proposal_md().replace("- danger: 0", "- danger 0")
    errors = proposal.validate(text, UNLOCKED)
    assert any("not a character, danger, target or starting_weapon bullet" in e for e in errors)


def test_next_run_rejects_non_integer_danger_without_doubled_prefix(proposal_md):
    errors = proposal.validate(proposal_md().replace("- danger: 0", "- danger: 1.5"), UNLOCKED)
    assert "## Next run: danger must be an integer: '1.5'" in errors


def test_valid_proposal_has_no_errors(proposal_md):
    assert proposal.validate(proposal_md(), UNLOCKED) == []


def test_crlf_proposal_is_read(proposal_md):
    assert proposal.validate(proposal_md().replace("\n", "\r\n"), UNLOCKED) == []


def test_validate_flags_wrong_section_order(proposal_md):
    text = proposal_md()
    swapped = (
        text.replace("## Why", "## Tmp").replace("## Risk", "## Why").replace("## Tmp", "## Risk")
    )
    errors = proposal.validate(swapped, UNLOCKED)
    assert any("sections must be" in e for e in errors)


def test_validate_flags_extra_second_level_heading(proposal_md):
    text = proposal_md().replace("## Risk", "## Notes\nx\n\n## Risk")
    assert any("sections must be" in e for e in proposal.validate(text, UNLOCKED))


def test_validate_flags_title_number_that_differs_from_file_name(proposal_md):
    errors = proposal.validate(proposal_md(), UNLOCKED, "2026-10-22-003.md")
    assert any("title is Proposal 1 but the file is number 3" in e for e in errors)
    assert proposal.validate(proposal_md(), UNLOCKED, "2026-10-22-001.md") == []


def test_validate_rejects_locked_character(proposal_md):
    errors = proposal.validate(proposal_md(), LOCKED)
    assert any("character_well_rounded is locked" in e for e in errors)


def test_validate_does_not_gate_a_character_absent_from_the_state(proposal_md):
    assert proposal.validate(proposal_md(), _state(characters={})) == []


def test_validate_rejects_plan_character_mismatch(proposal_md):
    text = proposal_md(plan_character="character_brawler")
    assert any("not the plan's character" in e for e in proposal.validate(text, UNLOCKED))


def test_validate_rejects_target_in_done(proposal_md):
    state = _state(done=[TARGET], open=[])
    errors = proposal.validate(proposal_md(), state)
    assert f"## Next run: target {TARGET} is not open (listed as done)" in errors


def test_validate_rejects_unknown_target(proposal_md):
    errors = proposal.validate(proposal_md(target="chal_nonexistent_9"), UNLOCKED)
    assert "## Next run: target chal_nonexistent_9 is not open (listed as unknown)" in errors


def test_validate_rejects_target_that_is_blocked(proposal_md):
    state = _state(open=[], blocked=[TARGET])
    errors = proposal.validate(proposal_md(), state)
    assert f"## Next run: target {TARGET} is not open (listed as blocked)" in errors


def test_validate_rejects_requires_character_mismatch(proposal_md):
    progress = {TARGET: {"requires_character": "character_brawler", "stat": "", "value": 5}}
    errors = proposal.validate(proposal_md(), _state(progress=progress))
    assert (
        f"## Next run: target {TARGET} needs character character_brawler, not {CHARACTER}" in errors
    )


def test_validate_passes_requires_character_null(proposal_md):
    progress = {TARGET: {"requires_character": None, "stat": "", "value": 5}}
    assert proposal.validate(proposal_md(), _state(progress=progress)) == []


def test_validate_target_none_passes_without_a_target_entry(proposal_md):
    text = proposal_md().replace(f"- target: {TARGET}", "- target: none")
    assert proposal.validate(text, _state(open=[], progress={})) == []


def test_validate_rejects_unfilled_template_placeholders():
    template = (REPO / "proposals" / "TEMPLATE.md").read_text(encoding="utf-8")
    errors = proposal.validate(template, UNLOCKED)
    assert "unfilled placeholder <character_id>" in errors


def test_template_has_the_section_order():
    text = (REPO / "proposals" / "TEMPLATE.md").read_text(encoding="utf-8")
    assert proposal._check_sections(text) == []


def test_skill_skeleton_lists_every_plan_key_the_mod_reads():
    skill = (REPO / ".claude" / "skills" / "brotato-next" / "SKILL.md").read_text(encoding="utf-8")
    skeleton = json.loads(re.search(r"```json\n(.*?)```", skill, re.DOTALL).group(1))
    gd = (REPO / "mod" / "Ellie-BrotatoBot" / "core" / "plan_file.gd").read_text(encoding="utf-8")
    table = re.search(r"const KEY_TYPES = \{(.*?)\n\}", gd, re.DOTALL).group(1)
    # prefer_sets is a plan key the harness writes (2026-10-23) and the mod does not read yet;
    # drop it from this set once the mod's KEY_TYPES carries it.
    assert set(skeleton["plan"]) - {"prefer_sets"} == set(re.findall(r'"(\w+)":', table))


def flat_rows(plans, character=CHARACTER, target=TARGET, profile=1):
    """``runs/index.json`` rows: one flat death at wave 10 per plan id."""
    return [
        {
            "run_id": f"r{i + 1}",
            "character_id": character,
            "plan_id": plan,
            "target_challenge": target,
            "outcome": "death",
            "death_wave": 10,
            "hp_end_last_wave": 5,
            "profile_id": profile,
            "target_fired": False,
        }
        for i, plan in enumerate(plans)
    ]


STAGNANT_ROWS = flat_rows(["a-v1", "a-v2", "a-v3"])
MUST_CHANGE = (
    f"stagnation is stagnant on {TARGET}: the plan family or the character must change "
    "(a new -vN alone is not a change)"
)


def test_validate_rejects_a_version_bump_after_stagnation(proposal_md):
    # O1: three flat deaths on a-v1..a-v3; a-v4 on the same character is not a change.
    errors = proposal.validate(proposal_md(plan_id="a-v4"), UNLOCKED, rows=STAGNANT_ROWS)
    assert errors == [MUST_CHANGE]


def test_validate_accepts_a_new_family_or_character_after_stagnation(proposal_md):
    assert proposal.validate(proposal_md(plan_id="b-v1"), UNLOCKED, rows=STAGNANT_ROWS) == []
    text = proposal_md(plan_id="a-v4", character="character_brawler")
    assert proposal.validate(text, UNLOCKED, rows=STAGNANT_ROWS) == []


def test_validate_change_check_skips_progress_and_missing_rows(proposal_md):
    text = proposal_md(plan_id="a-v4")
    assert proposal.validate(text, UNLOCKED) == []
    assert proposal.validate(text, UNLOCKED, rows=STAGNANT_ROWS[:2]) == []
    owner = flat_rows(["a-v1", "a-v2", "a-v3"], profile=0)
    assert proposal.validate(text, UNLOCKED, rows=owner) == []


def test_validate_change_check_on_escalate(proposal_md):
    rows = flat_rows(["x-v1", "x-v2", "x-v3", "a-v1", "a-v2", "a-v3"])
    errors = proposal.validate(proposal_md(plan_id="a-v4"), UNLOCKED, rows=rows)
    assert errors == [MUST_CHANGE.replace("is stagnant", "is escalate")]


def test_validate_change_check_uses_the_default_target_for_none(proposal_md):
    text = proposal_md(plan_id="a-v4").replace(f"- target: {TARGET}", "- target: none")
    errors = proposal.validate(text, _state(open=[], progress={}), rows=STAGNANT_ROWS)
    assert errors == [MUST_CHANGE]


def test_validate_rejects_plan_target_that_differs_from_next_run(proposal_md):
    # O8: the mod plays the plan's target, so it must be the validated one.
    errors = proposal.validate(proposal_md(plan_target="chal_other"), UNLOCKED)
    assert errors == [
        f"## Plan: target_challenge chal_other is not the ## Next run target {TARGET}"
    ]
    assert proposal.validate(proposal_md(plan_target=TARGET), UNLOCKED) == []
    assert proposal.validate(proposal_md(plan_target=""), UNLOCKED) == []
    none = proposal_md(plan_target="chal_other").replace(f"- target: {TARGET}", "- target: none")
    assert proposal.validate(none, UNLOCKED) == [
        "## Plan: target_challenge chal_other is not the ## Next run target none"
    ]


def test_validate_range_checks_danger(proposal_md):
    # O14: danger is 0..5.
    errors = proposal.validate(proposal_md().replace("- danger: 0", "- danger: 99"), UNLOCKED)
    assert errors == ["## Next run: danger must be 0 to 5, not 99"]
    assert proposal.validate(proposal_md().replace("- danger: 0", "- danger: 5"), UNLOCKED) == []
    errors = proposal.validate(proposal_md().replace("- danger: 0", "- danger: -1"), UNLOCKED)
    assert errors == ["## Next run: danger must be 0 to 5, not -1"]


def test_load_unlock_state_requires_the_bot_profile(tmp_path):
    path = tmp_path / "unlock_state.json"
    path.write_text(json.dumps({**UNLOCKED, "profile": 0}), encoding="utf-8")
    try:
        proposal.load_unlock_state(path)
    except ValueError as exc:
        assert str(exc) == f"{path} was built for profile 0; run unlock-state --profile 1"
    else:
        raise AssertionError("profile 0 state was accepted")
    path.write_text(json.dumps({**UNLOCKED, "profile": 1}), encoding="utf-8")
    assert proposal.load_unlock_state(path)["profile"] == 1


def _write_unlock_state(p, state=UNLOCKED):
    p.data_dir.mkdir(parents=True, exist_ok=True)
    p.data_dir.joinpath("unlock_state.json").write_text(json.dumps({**state, "profile": 1}))


def test_cli_validate_reads_the_run_index(tmp_paths, proposal_md, capsys):
    _write_unlock_state(tmp_paths)
    path = tmp_paths.project_root / "2026-10-22-001.md"
    path.write_text(proposal_md(plan_id="a-v4"), encoding="utf-8")
    assert cli.main(["proposal", "validate", str(path)]) == 0  # no index file
    assert capsys.readouterr().out.strip() == "ok"
    tmp_paths.runs_out.mkdir(parents=True, exist_ok=True)
    (tmp_paths.runs_out / "index.json").write_text(json.dumps(STAGNANT_ROWS), encoding="utf-8")
    assert cli.main(["proposal", "validate", str(path)]) == 1
    assert capsys.readouterr().out.strip() == MUST_CHANGE


def test_cli_validate_reads_a_bom_file(tmp_paths, proposal_md, capsys):
    # O13: a UTF-8 BOM is not part of the first heading.
    _write_unlock_state(tmp_paths)
    path = tmp_paths.project_root / "2026-10-22-001.md"
    path.write_bytes(b"\xef\xbb\xbf" + proposal_md().encode("utf-8"))
    assert cli.main(["proposal", "validate", str(path)]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_cli_validate_prints_non_ascii_errors_on_a_cp1252_stdout(
    tmp_paths, proposal_md, monkeypatch
):
    # O9: a piped Windows stdout is cp1252; the error list must print, not a traceback.
    _write_unlock_state(tmp_paths)
    path = tmp_paths.project_root / "2026-10-22-001.md"
    path.write_text(proposal_md().replace("## Target", "## Target → next"), encoding="utf-8")
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    assert cli.main(["proposal", "validate", str(path)]) == 1
    out.flush()
    text = out.buffer.getvalue().decode("utf-8")
    assert "sections must be" in text
    assert "## Target → next" in text


def test_cli_validate_prints_ok_and_errors(tmp_paths, proposal_md, capsys):
    _write_unlock_state(tmp_paths)
    good = tmp_paths.project_root / "2026-10-22-001.md"
    good.write_text(proposal_md(), encoding="utf-8")
    assert cli.main(["proposal", "validate", str(good)]) == 0
    assert capsys.readouterr().out.strip() == "ok"

    bad = tmp_paths.project_root / "bad.md"
    bad.write_text(proposal_md(plan_character="character_brawler"), encoding="utf-8")
    assert cli.main(["proposal", "validate", str(bad)]) == 1
    assert "not the plan's character" in capsys.readouterr().out


def test_cli_validate_refuses_without_unlock_state(tmp_paths, proposal_md, capsys):
    good = tmp_paths.project_root / "good.md"
    good.parent.mkdir(parents=True, exist_ok=True)
    good.write_text(proposal_md(), encoding="utf-8")
    assert cli.main(["proposal", "validate", str(good)]) == 1
    assert "unlock-state --profile 1" in capsys.readouterr().out


def test_cli_next_path_is_under_proposals_dir(tmp_paths, capsys):
    assert cli.main(["proposal", "next-path"]) == 0
    out = Path(capsys.readouterr().out.strip())
    assert out.parent == tmp_paths.proposals_dir
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-001\.md", out.name)


WEAPON_DATASET = {
    "characters": [{"id": CHARACTER, "starting_weapon_pool": ["Rock", "Revolver"]}],
    "weapons": [
        {"id": "weapon_rock", "display_name": "Rock"},
        {"id": "weapon_rock", "display_name": "Rock"},
        {"id": "weapon_revolver", "display_name": "Revolver"},
        {"id": "weapon_knife", "display_name": "Knife"},
    ],
}


def test_a_proposal_without_the_starting_weapon_bullet_stays_valid_as_any(proposal_md):
    legacy = proposal_md().replace("- starting_weapon: any\n", "")
    assert "starting_weapon" not in legacy.split("## Plan")[0]
    assert proposal.next_run(legacy)["starting_weapon"] == "any"
    assert proposal.validate(legacy, UNLOCKED) == []


def test_starting_weapon_must_come_after_target(proposal_md):
    text = proposal_md().replace(
        f"- target: {TARGET}\n- starting_weapon: any",
        f"- starting_weapon: any\n- target: {TARGET}",
    )
    assert any("needs the bullets" in e for e in proposal.validate(text, UNLOCKED))


def test_starting_weapon_any_or_a_pool_weapon_is_valid(proposal_md):
    for weapon in ("any", "weapon_rock", "weapon_revolver"):
        text = proposal_md(starting_weapon=weapon)
        assert proposal.validate(text, UNLOCKED, dataset=WEAPON_DATASET) == []


def test_starting_weapon_outside_the_characters_pool_is_rejected(proposal_md):
    text = proposal_md(starting_weapon="weapon_knife")
    errors = proposal.validate(text, UNLOCKED, dataset=WEAPON_DATASET)
    assert (
        f"## Next run: starting_weapon weapon_knife is not in {CHARACTER}'s starting pool" in errors
    )
    assert proposal.validate(text, UNLOCKED) == []  # no dataset: the pool is not checked


def test_locked_starting_weapon_is_rejected_when_the_state_has_the_lists(proposal_md):
    state = _state(weapons_unlocked=["weapon_revolver"])
    text = proposal_md(starting_weapon="weapon_rock")
    errors = proposal.validate(text, state, dataset=WEAPON_DATASET)
    assert "## Next run: starting_weapon weapon_rock is locked on the bot profile" in errors
    assert proposal.validate(proposal_md(starting_weapon="weapon_revolver"), state) == []
    assert proposal.validate(text, UNLOCKED, dataset=WEAPON_DATASET) == []  # lists absent
