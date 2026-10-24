import pytest

from brotato_bot import paths


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Paths with every location the run commands touch redirected into tmp_path."""
    env = {
        "APPDATA": str(tmp_path / "appdata"),
        "BROTATO_BOT_SAVE_DIR": str(tmp_path / "save"),
        "BROTATO_BOT_MOD_USER_DIR": str(tmp_path / "mod"),
        "BROTATO_BOT_PROJECT_ROOT": str(tmp_path / "project"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return paths.load(env)


@pytest.fixture
def proposal_md():
    """A valid proposal as text; keyword overrides build the failing variants."""

    def make(
        character="character_well_rounded",
        target="chal_gatherer_1",
        plan_character=None,
        plan_id="well-rounded-v1",
        plan_target=None,
        starting_weapon="any",
    ):
        plan_character = plan_character or character
        plan_target_line = (
            "" if plan_target is None else f'\n  "target_challenge": "{plan_target}",'
        )
        return f"""# Proposal 1

## Target
Work toward {target}, the next unlock on the bot profile.

## Next run
- character: {character}
- danger: 0
- target: {target}
- starting_weapon: {starting_weapon}

## Plan
```json
{{
  "plan_id": "{plan_id}",
  "character_id": "{plan_character}",{plan_target_line}
  "plan": {{"weapon_type": "ranged"}}
}}
```

## Why
The unlock is the cheapest open one (progress value 5). The guide favours ranged weapons.

## Risk
A ranged plan may die early; the stagnation check decides the next step.

## Stagnation check
fresh: no runs on any target
"""

    return make
