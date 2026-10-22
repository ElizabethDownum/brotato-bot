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
