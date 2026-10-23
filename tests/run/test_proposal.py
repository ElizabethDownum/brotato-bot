import json
import re
from datetime import date
from pathlib import Path

from brotato_bot import cli
from brotato_bot.run import proposal

UNLOCKED = {"characters": {"character_well_rounded": {"unlocked": True, "unlocked_by": None}}}
LOCKED = {"characters": {"character_well_rounded": {"unlocked": False, "unlocked_by": "chal_x"}}}


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
        "character_id": "character_well_rounded",
        "plan": {"weapon_type": "ranged"},
    }


def test_next_run_parses_three_bullets(proposal_md):
    assert proposal.next_run(proposal_md()) == {
        "character_id": "character_well_rounded",
        "danger": 0,
        "target": "chal_gatherer_1",
    }
    none = proposal_md().replace("- target: chal_gatherer_1", "- target: none")
    assert proposal.next_run(none)["target"] is None


def test_valid_proposal_has_no_errors(proposal_md):
    assert proposal.validate(proposal_md(), UNLOCKED) == []


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


def test_validate_rejects_locked_character(proposal_md):
    errors = proposal.validate(proposal_md(), LOCKED)
    assert any("character_well_rounded is locked" in e for e in errors)


def test_validate_does_not_gate_a_character_absent_from_the_state(proposal_md):
    assert proposal.validate(proposal_md(), {"characters": {}}) == []


def test_validate_rejects_plan_character_mismatch(proposal_md):
    text = proposal_md(plan_character="character_brawler")
    assert any("not the plan's character" in e for e in proposal.validate(text, UNLOCKED))


def test_cli_validate_prints_ok_and_errors(tmp_paths, proposal_md, capsys):
    tmp_paths.data_dir.mkdir(parents=True, exist_ok=True)
    tmp_paths.data_dir.joinpath("unlock_state.json").write_text(json.dumps(UNLOCKED))
    good = tmp_paths.project_root / "good.md"
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
