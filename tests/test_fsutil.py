from brotato_bot import fsutil


def test_atomic_write_leaves_no_tmp(tmp_path):
    f = tmp_path / "sub" / "a.txt"
    fsutil.atomic_write_text(f, "hello")
    assert f.read_text(encoding="utf-8") == "hello"
    assert list(f.parent.glob("*.tmp")) == []


def test_json_roundtrip(tmp_path):
    f = tmp_path / "a.json"
    fsutil.atomic_write_json(f, {"a": [1, 2]})
    assert fsutil.read_json(f) == {"a": [1, 2]}
    assert list(tmp_path.glob("*.tmp")) == []


def test_plain_name_accepts_run_and_request_ids():
    from brotato_bot.fsutil import plain_name

    for ok in ("20261022-201500-well_rounded-d0", "r-001", "a.b"):
        assert plain_name(ok) == ok


def test_plain_name_rejects_paths_and_specials():
    import pytest

    from brotato_bot.fsutil import plain_name

    for bad in (
        "",
        ".",
        "..",
        "../x",
        r"..\..\settings",
        "a/b",
        r"C:\x",
        "C:x",
        "/abs",
        "a b",
        "x\n",
    ):
        with pytest.raises(ValueError):
            plain_name(bad)
