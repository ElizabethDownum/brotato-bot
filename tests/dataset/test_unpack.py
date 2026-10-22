import struct
import sys

import pytest

from brotato_bot.dataset import unpack


def _write_pck(path, files, *, magic=b"GDPC", pack_format=1):
    """Write a minimal Godot 3 pck (format v1) holding ``files`` ({res path: bytes})."""
    header = magic + struct.pack("<IIII", pack_format, 3, 7, 0) + b"\x00" * 64
    header += struct.pack("<I", len(files))
    encoded = []
    for res_path in files:
        raw = res_path.encode("utf-8")
        raw += b"\x00" * (-len(raw) % 4)
        encoded.append(raw)
    index_size = sum(4 + len(raw) + 8 + 8 + 16 for raw in encoded)
    offset = len(header) + index_size
    index = b""
    blobs = b""
    for raw, data in zip(encoded, files.values(), strict=True):
        index += struct.pack("<I", len(raw)) + raw
        index += struct.pack("<QQ", offset + len(blobs), len(data)) + b"\x00" * 16
        blobs += data
    path.write_bytes(header + index + blobs)
    return path


def _all_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_unpack_round_trip(tmp_path):
    files = {
        "res://project.binary": b"\x01\x02\x03",
        "res://items/all/handcuffs/handcuffs_data.tres": b"[resource]\ntier = 2\n",
        "res://zones/zone_1/001/wave_1.tres": b"[resource]\ngroups_data = [  ]\n",
    }
    pck = _write_pck(tmp_path / "mini.pck", files)
    out = tmp_path / "out"

    assert unpack.unpack(pck, out) == 3
    assert _all_files(out) == sorted(k[len("res://") :] for k in files)
    for res_path, data in files.items():
        assert (out / res_path[len("res://") :]).read_bytes() == data


def test_unpack_rejects_bad_magic(tmp_path):
    pck = _write_pck(tmp_path / "bad.pck", {"res://a.txt": b"a"}, magic=b"NOPE")
    with pytest.raises(ValueError, match="Not a Godot PCK"):
        unpack.unpack(pck, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unpack_rejects_unsupported_format_version(tmp_path):
    pck = _write_pck(tmp_path / "v2.pck", {"res://a.txt": b"a"}, pack_format=2)
    with pytest.raises(ValueError, match="pack format v1"):
        unpack.unpack(pck, tmp_path / "out")
    assert not (tmp_path / "out").exists()


_DRIVE_RESET = pytest.param(
    "res://Z:/evil",  # a different drive makes os.path.join discard out_dir
    marks=pytest.mark.skipif(sys.platform != "win32", reason="Windows drive semantics"),
)


@pytest.mark.parametrize(
    "evil", ["res://../evil", "res://a/../../evil", "/../evil", "res://", _DRIVE_RESET]
)
def test_unpack_rejects_entry_outside_out_dir(tmp_path, evil):
    work = tmp_path / "work"
    work.mkdir()
    pck = _write_pck(tmp_path / "evil.pck", {"res://ok.txt": b"ok", evil: b"pwned"})
    out = work / "out"
    with pytest.raises(ValueError, match="resolves outside") as exc:
        unpack.unpack(pck, out)
    assert repr(evil) in str(exc.value)
    # Validation happens before any write: nothing extracted, nothing escaped.
    assert _all_files(tmp_path) == ["evil.pck"]
