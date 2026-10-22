"""Atomic file helpers."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_PLAIN_NAME = re.compile(r"[\w.-]+")


def plain_name(value: str) -> str:
    """Return ``value`` if it is a single plain file-name component (letters, digits,
    ``_``, ``.``, ``-``; not ``.`` or ``..``), else raise ValueError. Use it before
    joining an externally supplied name onto a directory."""
    if (
        not isinstance(value, str)
        or value in ("", ".", "..")
        or Path(value).name != value
        or not _PLAIN_NAME.fullmatch(value)
    ):
        raise ValueError(f"not a plain file name: {value!r}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
