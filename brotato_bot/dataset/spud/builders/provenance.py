# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
# brotato_bot.dataset.spud/builders/provenance.py
from __future__ import annotations


def detect_source(*, record: dict | None = None, entry: dict | None = None) -> str:
    """Return a record's content origin: "base" or a DLC tree name (e.g. "dlc_1").

    Ships defaulting to "base" for everything. On DLC day, teach THIS ONE
    function the real signal, in priority order (see
    docs/dlc-incorporation-playbook.md):

      1. Extraction origin (most likely + cleanest): if the DLC ships as a
         separate .pck, unpack it into a marked tree and pass the origin in via
         `entry`; echo it here.
      2. In-.tres flag / unlock gate: a `dlc`/`unlock` field readable off
         `record`.
      3. Directory prefix: a DLC-specific path segment (e.g. "abyssal/") on the
         record's source paths.

    Taught (brotato-bot Task 2c) with signal 1: the build unpacks each DLC pck
    into its own ``dlcs/<name>/`` tree and tags every record with ``dlc`` (the
    tree name, None for base); that tag is echoed here.
    """
    dlc = (record or {}).get("dlc") or (entry or {}).get("dlc")
    return str(dlc) if dlc else "base"
