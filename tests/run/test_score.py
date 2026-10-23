import json
import re
from pathlib import Path

import pytest

from brotato_bot import cli
from brotato_bot.run import score

REPO = Path(__file__).resolve().parents[2]


def fx(key, value):
    return {"key": key, "value": value}


def test_tier1_sized_effect_scores_the_weight():
    assert score.effect_score([fx("stat_speed", 3)], {"stat_speed": 7.0}) == 7.0
    assert score.effect_score([fx("stat_range", 15)], {"stat_range": 2.0}) == 2.0


def test_magnitude_scales_linearly():
    got = score.effect_score([fx("stat_speed", -10)], {"stat_speed": -14.0})
    assert got == pytest.approx(46.6666666667)


def test_cap_binds():
    assert score.effect_score([fx("stat_range", 300)], {"stat_range": 2.0}) == 8.0


def test_negative_value_on_positive_weight_subtracts():
    assert score.effect_score([fx("stat_armor", -2)], {"stat_armor": 4.0}) == -8.0


def test_unweighted_key_scores_zero():
    assert score.effect_score([fx("stat_luck", 5)], {"stat_armor": 4.0}) == 0.0


def test_boost_and_harvest_cap():
    boost = {"stat_dodge": 2.0}
    assert score.effect_score([fx("stat_dodge", 3)], {"stat_dodge": 3.0}, boost) == 6.0
    got = score.effect_score([fx("stat_harvesting", 5)], {"stat_harvesting": 10.0}, None, True)
    assert got == pytest.approx(1.5)
    assert score.effect_score([fx("stat_armor", 1)], {"stat_armor": 4.0}, None, True) == 4.0


def test_zero_and_junk_effects_are_skipped():
    fxs = [None, fx("stat_armor", 0), fx("stat_armor", 1)]
    assert score.effect_score(fxs, {"stat_armor": 4.0}) == 4.0


def test_item_score_adds_the_item_bonus():
    item = {"id": "item_x", "effects": [fx("stat_armor", 1)]}
    plan = {"stats": {"stat_armor": 4.0}, "item_bonus": {"item_x": 1.5}}
    assert score.item_score(item, plan) == 5.5
    assert score.item_score(item, {"stats": {"stat_armor": 4.0}}) == 4.0


def test_units_mirror_the_gdscript():
    text = (REPO / "mod/Ellie-BrotatoBot/shopping/effect_score.gd").read_text(encoding="utf-8")
    body = re.search(r"const UNITS = \{(.*?)\}", text, re.DOTALL).group(1)
    parsed = {k: float(v) for k, v in re.findall(r'"(\w+)":\s*([\d.]+)', body)}
    assert parsed == score.UNITS
    assert float(re.search(r"const MAX_UNITS = ([\d.]+)", text).group(1)) == score.MAX_UNITS


def test_units_match_the_game_tier1_upgrades():
    root = REPO / "data" / "extracted" / "items" / "upgrades"
    if not root.is_dir():
        pytest.skip("data/extracted is not present")
    found = {}
    for f in root.glob("*/1/*_effect.tres"):
        text = f.read_text(encoding="utf-8")
        key = re.search(r'^key = "(\w+)"', text, re.MULTILINE)
        value = re.search(r"^value = ([\d.]+)", text, re.MULTILINE)
        if key and value:
            found[key.group(1)] = float(value.group(1))
    assert found == score.UNITS


ITEMS = [
    {"id": "item_a", "tier": 1, "value": 10, "effects": [fx("stat_armor", 2)]},
    {"id": "item_b", "tier": 2, "value": 20, "effects": [fx("stat_armor", -1), fx("knockback", 3)]},
    {"id": "item_c", "tier": 1, "value": 5, "effects": [fx("stat_dodge", 3)]},
]


def _run(tmp_path, monkeypatch, argv):
    from brotato_bot import paths

    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "brotato.json").write_text(json.dumps({"items": ITEMS}), encoding="utf-8")
    real = paths.load()
    monkeypatch.setattr(
        paths, "load", lambda: real.__class__(**{**real.__dict__, "data_dir": data})
    )
    return cli.main(argv)


def test_cli_score_plan_lists_items_by_score(tmp_path, monkeypatch, capsys):
    plan = tmp_path / "plan.json"
    body = {"stats": {"stat_armor": 4.0, "stat_dodge": 1.0}, "item_bonus": {"item_c": 1.5}}
    body["min_buy"] = 2.0
    plan.write_text(json.dumps({"plan_id": "p-v1", "character_id": "c", "plan": body}))
    assert _run(tmp_path, monkeypatch, ["score", "--plan", str(plan)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "p-v1" in lines[0] and "as given" in lines[0]
    ids = [ln.split()[1] for ln in lines[2:-1]]
    assert ids == ["item_a", "item_c", "item_b"]
    assert "stat_armor:+2" in lines[2]
    assert lines[-1] == "2 of 3 items score above min_buy 2"
    assert _run(tmp_path, monkeypatch, ["score", "--plan", str(plan), "--min-buy", "6"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1 of 3 items score above min_buy 6"


def test_cli_score_proposal_block(tmp_path, monkeypatch, capsys):
    plan = {"plan_id": "p-v1", "character_id": "c", "plan": {"stats": {"stat_armor": 4.0}}}
    md = tmp_path / "p.md"
    md.write_text("## Plan\n```json\n" + json.dumps(plan) + "\n```\n", encoding="utf-8")
    assert _run(tmp_path, monkeypatch, ["score", "--proposal", str(md)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1 of 3 items score above min_buy 0"


def test_conditional_effect_counts_one_unit_at_most():
    cond = {"key": "stat_attack_speed", "value": 40, "text_key": "effect_stat_while_not_moving"}
    plain = {"key": "stat_attack_speed", "value": 40, "text_key": ""}
    assert score.effect_score([cond], {"stat_attack_speed": 7.0}) == 7.0
    assert score.effect_score([plain], {"stat_attack_speed": 7.0}) == 28.0
