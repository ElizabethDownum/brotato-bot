from dlc_tree import BASE_NAMES, DLC_NAMES, make_tree

from brotato_bot.dataset.spud.builders import discover


def _by_dlc(entries, id_key):
    out: dict = {}
    for e in entries:
        out.setdefault(e["dlc"], []).append(e[id_key])
    return out


def test_discover_finds_dlc_character_item_weapon_set_enemy(tmp_path):
    root = str(make_tree(tmp_path))
    b, d = BASE_NAMES, DLC_NAMES

    assert _by_dlc(discover.find_item_dirs(root), "item_id") == {
        None: [f"item_{b['item']}"],
        "dlc_1": [f"item_{d['item']}"],
    }
    assert _by_dlc(discover.find_character_dirs(root), "char_id") == {
        None: [f"character_{b['character']}"],
        "dlc_1": [f"character_{d['character']}"],
    }
    assert _by_dlc(discover.find_weapon_dirs(root), "weapon_id") == {
        None: [f"weapon_{b['weapon']}"],
        "dlc_1": [f"weapon_{d['weapon']}"],
    }
    assert _by_dlc(discover.find_set_dirs(root), "set_id") == {
        None: [f"set_{b['set']}"],
        "dlc_1": [f"set_{d['set']}"],
    }
    assert _by_dlc(discover.find_enemy_dirs(root), "enemy_id") == {
        None: [b["enemy"]],
        "dlc_1": [d["enemy"]],
    }


def test_discover_dlc_effects_live_in_effects_subdir(tmp_path):
    root = str(make_tree(tmp_path))
    items = {e["item_id"]: e for e in discover.find_item_dirs(root)}
    chars = {e["char_id"]: e for e in discover.find_character_dirs(root)}
    for entry in (items[f"item_{DLC_NAMES['item']}"], chars[f"character_{DLC_NAMES['character']}"]):
        assert len(entry["effect_paths"]) == 1
        assert "effects" in entry["effect_paths"][0].replace("\\", "/").split("/")
    assert len(items[f"item_{BASE_NAMES['item']}"]["effect_paths"]) == 1


def test_content_sources_lists_base_then_each_dlc(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "dlcs" / "dlc_2").mkdir()
    sources = discover.content_sources(str(tmp_path))
    assert [s.dlc for s in sources] == [None, "dlc_1", "dlc_2"]


def test_coverage_report_accounts_dlcs_tree(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "dlcs" / "dlc_1" / "bosses").mkdir()
    report = discover.coverage_report(str(tmp_path))
    assert "dlcs" not in report["unclaimed_trees"]
    assert "dlcs/dlc_1/bosses" in report["unclaimed_trees"]


def test_weapon_scaling_on_dlc_curse_stat_builds():
    # Abyssal Terrors weapons (anchor, trident, captains_sword) scale with stat_curse.
    from brotato_bot.dataset.spud.builders.weapons import build_weapon_record

    stats = (
        "[resource]\ndamage = 20\ncooldown = 40\n"
        'scaling_stats = [ [ "stat_melee_damage", 1.0 ], [ "stat_curse", 0.5 ] ]\n'
    )
    rec = build_weapon_record(stats, "[resource]\n", weapon_id="weapon_test", name="T", tier=2)
    assert rec["id"] == "weapon_test"


def test_discover_emits_one_item_per_tier_data_file(tmp_path):
    from dlc_tree import TIERED_ITEM, add_tiered_dlc_item

    root = make_tree(tmp_path)
    add_tiered_dlc_item(root)
    items = [e for e in discover.find_item_dirs(str(root)) if TIERED_ITEM in e["item_id"]]
    assert [e["item_id"] for e in items] == [f"item_{TIERED_ITEM}_0", f"item_{TIERED_ITEM}_1"]
    assert all(e["dlc"] == "dlc_1" for e in items)
    names = [
        sorted(p.replace("\\", "/").rsplit("/", 1)[1] for p in e["effect_paths"]) for e in items
    ]
    assert names == [
        [f"{TIERED_ITEM}_effect_0.tres", f"{TIERED_ITEM}_effect_shared.tres"],
        [f"{TIERED_ITEM}_1_effect.tres", f"{TIERED_ITEM}_effect_shared.tres"],
    ]


def test_build_dataset_tiered_dlc_item_records(tmp_path):
    from dlc_tree import TIERED_ITEM, add_tiered_dlc_item

    from brotato_bot.dataset.build import build_dataset

    root = make_tree(tmp_path / "extracted")
    add_tiered_dlc_item(root)
    ds = build_dataset(root, tmp_path / "out.json", "1.1.15.4", generated_at="2026-10-22T00:00:00Z")
    recs = {r["id"]: r for r in ds["items"] if TIERED_ITEM in r["id"]}
    assert sorted(recs) == [f"item_{TIERED_ITEM}_0", f"item_{TIERED_ITEM}_1"]
    keys = {i: sorted(e["key"] for e in r["effects"]) for i, r in recs.items()}
    assert keys == {
        f"item_{TIERED_ITEM}_0": ["stat_armor", "stat_engineering"],
        f"item_{TIERED_ITEM}_1": ["stat_engineering", "stat_range"],
    }
    assert {r["tier"] for r in recs.values()} == {1, 2}
