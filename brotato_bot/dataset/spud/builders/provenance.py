# Folded from Spud Coach (MIT) commit 9e02315, see learnings/upstream.md
# brotato_bot.dataset.spud/builders/provenance.py
from __future__ import annotations


def detect_source(*, record: dict | None = None, entry: dict | None = None) -> str:  # noqa: ARG001 - unused today; this is the seam DLC detection will read from
    """Return a record's content origin: "base" or a DLC id (e.g. "abyssal_terrors").

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

    Until taught, every record is base-game content.
    """
    return "base"
