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
