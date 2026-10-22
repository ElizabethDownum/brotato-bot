# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
from brotato_bot.dataset.spud.builders.version import parse_game_version

PROGRESS_DATA_GD = '''extends Node

const VERSION = "1.1.15.4"
const VERSION_SWITCH = "1.1.13.2"

var settings := {}
'''


def test_parse_game_version_finds_version_constant():
    assert parse_game_version(PROGRESS_DATA_GD) == "1.1.15.4"


def test_parse_game_version_returns_none_when_absent():
    assert parse_game_version("extends Node\nvar x = 1\n") is None


def test_parse_game_version_ignores_version_switch_only():
    text = 'extends Node\nconst VERSION_SWITCH = "1.1.13.2"\n'
    assert parse_game_version(text) is None
