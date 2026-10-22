# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
"""Unpacker for Godot 3.x .pck archives (pack format version 1).

Parses the file index and extracts every entry, preserving the res:// path
layout under an output directory. Stdlib only; no dependencies.

Raises ValueError on a bad magic, an unsupported pack format, or an entry whose
destination would fall outside the output directory.
"""
import os
import struct
from collections import Counter

MAGIC = b"GDPC"


def read_u32(f):
    return struct.unpack("<I", f.read(4))[0]


def read_u64(f):
    return struct.unpack("<Q", f.read(8))[0]


def _is_inside(root, dest):
    """True if resolved ``dest`` is strictly below resolved ``root``."""
    try:
        return dest != root and os.path.commonpath([root, dest]) == root
    except ValueError:  # different drives on Windows
        return False


def unpack(pck_path, out_dir):
    with open(pck_path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Not a Godot PCK: magic={magic!r} (expected {MAGIC!r})")

        pack_format = read_u32(f)
        ver_major = read_u32(f)
        ver_minor = read_u32(f)
        ver_patch = read_u32(f)
        print(f"PCK format v{pack_format}, Godot {ver_major}.{ver_minor}.{ver_patch}")
        if pack_format != 1:
            raise ValueError(f"Only pack format v1 supported here (got v{pack_format}).")

        # 16 reserved uint32 fields
        f.read(16 * 4)

        file_count = read_u32(f)
        print(f"File count: {file_count}")

        entries = []
        for _ in range(file_count):
            path_len = read_u32(f)
            raw_path = f.read(path_len)
            path = raw_path.rstrip(b"\x00").decode("utf-8")
            offset = read_u64(f)
            size = read_u64(f)
            f.read(16)  # md5, ignored
            entries.append((path, offset, size))

        # Resolve and check every destination before writing anything, so a hostile
        # entry (res://../x, an absolute or drive-qualified path) aborts the unpack
        # with nothing written for it.
        root = os.path.realpath(out_dir)
        planned = []
        for path, offset, size in entries:
            rel = path[len("res://"):] if path.startswith("res://") else path.lstrip("/")
            dest = os.path.realpath(os.path.join(root, *rel.split("/")))
            if not _is_inside(root, dest):
                raise ValueError(f"pck entry {path!r} resolves outside {out_dir}")
            planned.append((rel, dest, offset, size))

        ext_counter = Counter()
        total_bytes = 0
        for rel, dest, offset, size in planned:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.seek(offset)
            data = f.read(size)
            with open(dest, "wb") as out:
                out.write(data)
            ext_counter[os.path.splitext(rel)[1].lower()] += 1
            total_bytes += size

    print(f"\nExtracted {len(entries)} files, {total_bytes/1_048_576:.1f} MiB")
    print("Top extensions:")
    for ext, n in ext_counter.most_common(15):
        print(f"  {ext or '(none)':10} {n}")
    return len(entries)

