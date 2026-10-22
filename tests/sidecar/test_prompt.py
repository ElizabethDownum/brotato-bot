import json
from pathlib import Path

from brotato_bot.dataset.unlocks import Challenge
from brotato_bot.sidecar import prompt

FIXTURES = Path(__file__).parent / "fixtures"
RUN_ID = "20261022-201500-well_rounded-d0"
SECTIONS = [
    "## Objective",
    "## State",
    "## Options",
    "## Plan",
    "## Relevant knowledge",
    "## Past decisions",
    "## Answer format",
]

# A hand-written slice of data/brotato.json (which is gitignored): two offered ids,
# the character and one set. Weapon records are per family id with tier 1-4.
DATASET = {
    "weapons": [
        {
            "id": "weapon_smg",
            "name": "Smg",
            "display_name": "SMG",
            "tier": 1,
            "weapon_type": "ranged",
            "base_damage": 3.0,
            "cooldown": 4.0,
            "max_range": 400.0,
            "crit_chance": 0.01,
            "scaling_stats": [["stat_ranged_damage", 0.5]],
            "sets": ["Gun"],
            "effects": [],
            "dlc": None,
            "source": "base",
        },
        {
            "id": "weapon_smg",
            "name": "Smg",
            "display_name": "SMG",
            "tier": 2,
            "weapon_type": "ranged",
            "base_damage": 4.0,
            "cooldown": 4.0,
            "scaling_stats": [["stat_ranged_damage", 0.6]],
            "sets": ["Gun"],
            "effects": [],
            "dlc": None,
            "source": "base",
        },
    ],
    "items": [
        {
            "id": "item_bag",
            "name": "Bag",
            "display_name": "Bag",
            "tier": 1,
            "value": 15,
            "tags": ["stat_luck", "economy"],
            "effects": [
                {"key": "item_box_gold", "value": 15, "text": ""},
                {"key": "stat_speed", "value": -1, "text": ""},
            ],
            "dlc": None,
            "source": "base",
        },
    ],
    "characters": [
        {
            "id": "character_well_rounded",
            "name": "Well Rounded",
            "display_name": "Well-Rounded",
            "flat_bonuses": [{"stat": "stat_max_hp", "value": 5}],
            "gain_modifiers": [],
            "special_effects": [],
            "dlc": None,
        },
    ],
    "sets": [
        {
            "id": "set_gun",
            "name": "Gun",
            "display_name": "Gun",
            "bonuses": [{"count": 2, "effect": {"key": "stat_range", "value": 10}}],
        },
    ],
}

PLAN = {
    "plan_id": "well-rounded-v1",
    "character_id": "character_well_rounded",
    "target_challenge": "chal_gatherer_1",
    "plan": {"weapon_type": "ranged", "stats": {"stat_ranged_damage": 9.0}},
}

GATHERER = Challenge(
    id="chal_gatherer_1",
    hash=0,
    name_key="CHAL_GATHERER",
    name_en="Gatherer {0}",
    desc_en="Collect {0} materials",
    reward_kind=None,
    reward_id=None,
    stat="",
    number=1,
    value=300,
    unlocked_by_default=False,
    requires_character=None,
)

KNOWLEDGE = {
    "character-well-rounded": (
        "---\nsource: Well Rounded\nfetched_at: 2026-10-22T00:00:00+00:00\n---\n"
        "Intro paragraph about nothing.\n\n"
        "Well Rounded gains max HP, speed and harvesting.\n"
    ),
    "items": "The Bag gives gold from crates.\n\nUnrelated paragraph.\n",
}


def _state():
    return json.loads((FIXTURES / "state_shop.json").read_text(encoding="utf-8"))


def _request(**over):
    req = {
        "id": f"{RUN_ID}-002",
        "kind": "shop",
        "screen": "shop",
        "run_id": RUN_ID,
        "seq": 2,
        "state_path": f"user://brotato-bot/state/{RUN_ID}-002.json",
        "options": [
            {"index": 0, "id": "weapon_smg_1", "kind": "weapon", "price": 25, "score": 6.5},
            {"index": 1, "id": "item_bag", "kind": "item", "price": 20, "score": 2.0},
        ],
        "deadline_ms": 1761160591000,
    }
    req.update(over)
    return req


def _unlock_state():
    return {
        "profile": 1,
        "done": [],
        "open": ["chal_gatherer_1"],
        "blocked": [],
        "progress": {
            "chal_gatherer_1": {"requires_character": None, "stat": "", "number": 1, "value": 300},
        },
        "challenges": prompt.challenge_texts([GATHERER], DATASET),
    }


EXPERIENCE = [
    {
        "run_id": "20261021-190000-well_rounded-d0",
        "kind": "shop",
        "character_id": "character_well_rounded",
        "wave": 3,
        "action": "buy",
        "chosen": "weapon_smg_1",
        "source": "haiku",
        "confidence": 0.7,
        "outcome": "death",
        "death_wave": 6,
        "hp_next_wave": 4,
        "kept_to_end": True,
    },
]


def _sections_positions(text):
    return [text.find(h) for h in SECTIONS]


def test_prompt_sections_in_order():
    text = prompt.build(_request(), _state(), PLAN, DATASET, _unlock_state(), KNOWLEDGE, EXPERIENCE)
    pos = _sections_positions(text)
    assert all(p >= 0 for p in pos), dict(zip(SECTIONS, pos, strict=True))
    assert pos == sorted(pos)

    options = text[pos[2] : pos[3]]
    # Each offered id appears with its dataset record (tier-1 SMG, not tier 2).
    assert "weapon_smg_1" in options
    assert '"base_damage": 3.0' in options
    assert '"base_damage": 4.0' not in options
    assert "Gun" in options and "stat_range" in options  # set and its bonus
    assert "item_bag" in options
    assert "item_box_gold" in options
    assert "price 25" in options and "price 20" in options

    objective = text[pos[0] : pos[1]]
    assert "chal_gatherer_1" in objective
    assert "Collect 300 materials" in objective

    state = text[pos[1] : pos[2]]
    assert "Well-Rounded" in state and "gold 44" in state
    assert "locked" in state

    knowledge = text[pos[4] : pos[5]]
    assert "Well Rounded gains max HP" in knowledge
    assert "The Bag gives gold" in knowledge
    assert "Intro paragraph" not in knowledge and "Unrelated" not in knowledge

    past = text[pos[5] : pos[6]]
    assert "20261021-190000-well_rounded-d0" in past and "death_wave 6" in past

    answer = text[pos[6] :]
    assert "options[]" in answer and "never" in answer


def test_prompt_without_target_states_optimise_objective():
    state = _state()
    state["target_challenge"] = ""
    plan = dict(PLAN, target_challenge="")
    text = prompt.build(_request(), state, plan, DATASET, {}, {}, [])
    pos = _sections_positions(text)
    objective = text[pos[0] : pos[1]]
    assert "no unlock target: optimise this character's run" in objective
    assert "none yet" in text[pos[5] : pos[6]]


def test_prompt_renders_missing_ids_without_raising():
    req = _request(
        options=[
            {"index": 0, "id": "item_does_not_exist", "kind": "item", "price": 9, "score": 1.0},
        ]
    )
    text = prompt.build(req, _state(), PLAN, DATASET, {}, {}, [])
    assert "unknown item item_does_not_exist" in text


def test_prompt_target_falls_back_to_id_and_progress():
    unlock = {
        "progress": {
            "chal_gatherer_1": {"requires_character": None, "stat": "", "number": 1, "value": 300}
        }
    }
    text = prompt.build(_request(), _state(), PLAN, DATASET, unlock, {}, [])
    objective = text[: text.find("## State")]
    assert "chal_gatherer_1" in objective and "300" in objective


def test_challenge_texts_formats_character_challenge():
    mage = Challenge(
        id="chal_well_rounded",
        hash=0,
        name_key="CHARACTER_WELL_ROUNDED",
        name_en="Well Rounded",
        desc_en="Win a run with {0}",
        reward_kind=None,
        reward_id=None,
        stat="",
        number=0,
        value=1,
        unlocked_by_default=False,
        requires_character="character_well_rounded",
    )
    untranslated = Challenge(
        **{**mage.__dict__, "id": "chal_x", "name_en": "CHARACTER_WELL_ROUNDED"}
    )
    texts = prompt.challenge_texts([mage, untranslated, GATHERER], DATASET)
    assert texts["chal_well_rounded"]["description"] == "Win a run with Well Rounded"
    # Without translations the name is its key: the dataset's display name stands in.
    assert texts["chal_x"]["description"] == "Win a run with Well-Rounded"
    assert texts["chal_gatherer_1"] == {
        "name": "Gatherer 1",
        "description": "Collect 300 materials",
    }


def test_levelup_options_render_stat_and_value():
    req = _request(
        kind="levelup",
        screen="levelup",
        options=[
            {"index": 0, "id": "upgrade_armor_1", "stat": "stat_armor", "value": 1, "score": 3.0},
        ],
    )
    text = prompt.build(req, _state(), PLAN, DATASET, {}, {}, [])
    options = text[text.find("## Options") : text.find("## Plan")]
    assert "upgrade_armor_1" in options and "stat_armor +1" in options
    assert "unknown item" not in options


def test_system_prompts_embed_the_schema_exactly():
    schema_text = prompt.SCHEMA_PATH.read_text(encoding="utf-8").strip()
    for kind in ("shop", "levelup", "pivot", "checkpoint"):
        system = prompt.system_prompt(kind)
        assert schema_text in system
        assert "{{" not in system
    assert prompt.system_prompt("checkpoint") != prompt.system_prompt("shop")
