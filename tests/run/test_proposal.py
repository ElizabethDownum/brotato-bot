import json
import re
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


def test_next_run_parses_three_bullets(proposal_md):
    assert proposal.next_run(proposal_md()) == {
        "character_id": CHARACTER,
        "danger": 0,
        "target": TARGET,
    }
    none = proposal_md().replace(f"- target: {TARGET}", "- target: none")
    assert proposal.next_run(none)["target"] is None


def test_next_run_rejects_duplicate_bullet(proposal_md):
    text = proposal_md().replace("- danger: 0", "- danger: 0\n- danger: 1")
    errors = proposal.validate(text, UNLOCKED)
    assert any("exactly three bullets" in e for e in errors)


def test_next_run_rejects_extra_bullet(proposal_md):
    text = proposal_md().replace(f"- target: {TARGET}", f"- target: {TARGET}\n- note: anything")
    errors = proposal.validate(text, UNLOCKED)
    assert any("not a character, danger or target bullet" in e for e in errors)


def test_next_run_rejects_unknown_bullet_text(proposal_md):
    text = proposal_md().replace("- danger: 0", "- danger 0")
    errors = proposal.validate(text, UNLOCKED)
    assert any("not a character, danger or target bullet" in e for e in errors)


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
    assert set(skeleton["plan"]) == set(re.findall(r'"(\w+)":', table))


def test_cli_validate_prints_ok_and_errors(tmp_paths, proposal_md, capsys):
    tmp_paths.data_dir.mkdir(parents=True, exist_ok=True)
    tmp_paths.data_dir.joinpath("unlock_state.json").write_text(json.dumps(UNLOCKED))
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
