from pathlib import Path

from test_unpack import _write_pck

from brotato_bot import cli


def test_dataset_build_command_registered():
    args = cli.build_parser().parse_args(["dataset", "build", "--pck", "x.pck", "--out", "o.json"])
    assert args.pck == "x.pck"
    assert args.out == "o.json"
    assert callable(args.func)


def test_dataset_build_fails_fast_without_version(tmp_path, monkeypatch, capsys):
    from brotato_bot.dataset import unpack

    pck = tmp_path / "noversion.pck"
    pck.write_bytes(b"GDPC" + b"\x00" * 64)
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    called = []
    monkeypatch.setattr(unpack, "unpack", lambda *a, **k: called.append(a))

    assert cli.main(["dataset", "build", "--pck", str(pck)]) == 1
    assert called == []  # the unpack never started
    assert "no game version" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def _patch_build(monkeypatch, calls):
    from brotato_bot.dataset import build, unpack, version

    real_unpack = unpack.unpack

    def spy_unpack(pck, out):
        calls.append(Path(pck).name)
        return real_unpack(pck, out)

    monkeypatch.setattr(version, "detect_game_version", lambda pck: "9.9.9.9")
    monkeypatch.setattr(unpack, "unpack", spy_unpack)
    monkeypatch.setattr(build, "build_dataset", lambda *a, **k: None)


def test_build_unpacks_dlc_after_base(tmp_path, monkeypatch, capsys):
    base = _write_pck(tmp_path / "base.pck", {"res://a.txt": b"base", "res://only_base.txt": b"b"})
    dlc = _write_pck(tmp_path / "dlc.pck", {"res://a.txt": b"dlc", "res://only_dlc.txt": b"d"})
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    calls: list[str] = []
    _patch_build(monkeypatch, calls)

    assert cli.main(["dataset", "build", "--pck", str(base), "--dlc-pck", str(dlc)]) == 0
    extracted = tmp_path / "data" / "extracted"
    assert (extracted / "a.txt").read_bytes() == b"dlc"
    assert (extracted / "only_base.txt").is_file()
    assert (extracted / "only_dlc.txt").is_file()
    assert calls == ["base.pck", "dlc.pck"]
    out = capsys.readouterr().out
    assert f"Unpacked base pck: {base}" in out
    assert f"Unpacked DLC pck: {dlc}" in out


def test_build_skips_missing_dlc(tmp_path, monkeypatch, capsys):
    base = _write_pck(tmp_path / "base.pck", {"res://a.txt": b"base"})
    missing = tmp_path / "nope.pck"
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    calls: list[str] = []
    _patch_build(monkeypatch, calls)

    assert cli.main(["dataset", "build", "--pck", str(base), "--dlc-pck", str(missing)]) == 0
    assert f"DLC pck not found: {missing} (skipping)" in capsys.readouterr().out
    assert calls == ["base.pck"]
    assert (tmp_path / "data" / "extracted" / "a.txt").read_bytes() == b"base"


def test_build_dlc_none(tmp_path, monkeypatch):
    base = _write_pck(tmp_path / "base.pck", {"res://a.txt": b"base"})
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    # The default DLC pck exists, but "none" must never open it.
    default_dlc = _write_pck(tmp_path / "default_dlc.pck", {"res://a.txt": b"dlc"})
    monkeypatch.setenv("BROTATO_BOT_DLC_PCK", str(default_dlc))
    calls: list[str] = []
    _patch_build(monkeypatch, calls)

    assert cli.main(["dataset", "build", "--pck", str(base), "--dlc-pck", "none"]) == 0
    assert calls == ["base.pck"]
    assert (tmp_path / "data" / "extracted" / "a.txt").read_bytes() == b"base"


def test_build_uses_default_dlc_pck(tmp_path, monkeypatch):
    base = _write_pck(tmp_path / "base.pck", {"res://a.txt": b"base"})
    dlc = _write_pck(tmp_path / "AT.pck", {"res://a.txt": b"dlc"})
    monkeypatch.setenv("BROTATO_BOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BROTATO_BOT_DLC_PCK", str(dlc))
    calls: list[str] = []
    _patch_build(monkeypatch, calls)

    assert cli.main(["dataset", "build", "--pck", str(base)]) == 0
    assert calls == ["base.pck", "AT.pck"]
