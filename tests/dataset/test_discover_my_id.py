"""Records are keyed by the game's ``my_id``, not the folder name (completion fix F2)."""

from dlc_tree import RENAMED, add_renamed_content, make_tree

from brotato_bot.dataset.build import build_dataset
from brotato_bot.dataset.spud.builders import discover


def test_discover_keys_weapons_and_items_by_my_id(tmp_path):
    root = str(add_renamed_content(make_tree(tmp_path)))
    weapons = {e["weapon_id"]: e for e in discover.find_weapon_dirs(root)}
    assert "weapon_test_club" in weapons and f"weapon_{RENAMED['weapon']}" not in weapons
    assert weapons["weapon_test_club"]["tier"] == 1
    assert weapons["weapon_test_club"]["name"] == "Test Mace"  # folder name stays the fallback
    items = {e["item_id"] for e in discover.find_item_dirs(root)}
    assert {"item_test_lens", "item_test_hourglass", "item_test_broken_hourglass"} <= items
    assert f"item_{RENAMED['item']}" not in items


def test_build_dataset_uses_my_id_and_keeps_starting_pool(tmp_path):
    root = add_renamed_content(make_tree(tmp_path / "extracted"))
    ds = build_dataset(root, tmp_path / "out.json", "1.1.15.4", generated_at="2026-10-22T00:00:00Z")
    weapon = next(w for w in ds["weapons"] if w["id"] == "weapon_test_club")
    assert {"item_test_lens", "item_test_hourglass", "item_test_broken_hourglass"} <= {
        i["id"] for i in ds["items"]
    }
    char = next(c for c in ds["characters"] if c["id"] == f"character_{RENAMED['character']}")
    assert char["starting_weapon_pool"] == [weapon.get("display_name") or weapon["name"]]
