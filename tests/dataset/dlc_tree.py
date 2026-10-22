"""Synthetic base + ``dlcs/dlc_1`` extracted tree for the DLC discovery/build tests.

Every resource here is hand-written in the Godot 3 ``.tres`` shape; nothing is copied
from game files. The DLC half follows the measured Abyssal Terrors layout:
``dlcs/<dlc>/{characters,items,sets,weapons,enemies}`` with item and character effects
in an ``effects/`` subfolder.
"""

from __future__ import annotations

from pathlib import Path

_ITEM_DATA = """[gd_resource type="Resource" load_steps=2 format=2]

[ext_resource path="res://items/global/item_data.gd" type="Script" id=1]

[resource]
script = ExtResource( 1 )
my_id = "{my_id}"
name = "{name_key}"
tier = 1
value = 30
tags = [  ]
"""
_EFFECT = '[resource]\nkey = "stat_armor"\nvalue = 1\neffect_sign = 3\ntext_key = ""\n'
_CHAR_DATA = """[gd_resource type="Resource" format=2]

[resource]
my_id = "{my_id}"
name = "{name_key}"
wanted_tags = [  ]
banned_item_groups = [  ]
"""
_WEAPON_STATS = "[resource]\ndamage = 6\ncooldown = 30\n"
_WEAPON_DATA = '[resource]\nmy_id = "{my_id}"\nweapon_id = "{weapon_id}"\nname = "{name_key}"\n'
_SET_DATA = '[resource]\nmy_id = "{my_id}"\nname = "{name_key}"\n'
_SET_EFFECT = '[resource]\nkey = "stat_armor"\nvalue = 2\n'
_ENEMY_STATS = "[resource]\nhealth = 9\n"


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _content(
    root: Path,
    *,
    items: str,
    characters: str,
    sets: str,
    weapons: str,
    enemies: str,
    names: dict[str, str],
    effects_subdir: str,
) -> None:
    item, char, wpn, st, enemy = (
        names["item"],
        names["character"],
        names["weapon"],
        names["set"],
        names["enemy"],
    )
    d = root / items / item
    _w(d / f"{item}_data.tres", _ITEM_DATA.format(my_id=f"item_{item}", name_key=item.upper()))
    _w(d / effects_subdir / f"{item}_effect_0.tres", _EFFECT)
    d = root / characters / char
    _w(
        d / f"{char}_data.tres",
        _CHAR_DATA.format(my_id=f"character_{char}", name_key=f"CHARACTER_{char.upper()}"),
    )
    _w(d / effects_subdir / f"{char}_effect_0.tres", _EFFECT)
    d = root / weapons / "melee" / wpn / "1"
    _w(d / f"{wpn}_stats.tres", _WEAPON_STATS)
    _w(
        d / f"{wpn}_data.tres",
        _WEAPON_DATA.format(
            my_id=f"weapon_{wpn}_1", weapon_id=f"weapon_{wpn}", name_key=wpn.upper()
        ),
    )
    d = root / sets / st
    _w(d / f"{st}_set_data.tres", _SET_DATA.format(my_id=f"set_{st}", name_key=st.upper()))
    _w(d / "2" / "set_2_effect_1.tres", _SET_EFFECT)
    d = root / enemies / enemy
    _w(d / f"{enemy}_stats.tres", _ENEMY_STATS)


BASE_NAMES = {
    "item": "test_anvil",
    "character": "test_ranger",
    "weapon": "test_knife",
    "set": "test_blade",
    "enemy": "test_alien",
}
DLC_NAMES = {
    "item": "test_shell",
    "character": "test_diver",
    "weapon": "test_spoon",
    "set": "test_naval",
    "enemy": "test_crab",
}


def make_tree(root: Path) -> Path:
    """Write one item, character, weapon tier, set and enemy for base and dlc_1."""
    _content(
        root,
        items="items/all",
        characters="items/characters",
        sets="items/sets",
        weapons="weapons",
        enemies="entities/units/enemies",
        names=BASE_NAMES,
        effects_subdir=".",
    )
    _content(
        root / "dlcs" / "dlc_1",
        items="items",
        characters="characters",
        sets="sets",
        weapons="weapons",
        enemies="enemies",
        names=DLC_NAMES,
        effects_subdir="effects",
    )
    return root
