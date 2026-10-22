"""Experience log: past sidecar decisions joined with how the run turned out.

Two JSONL files, one JSON object per line, appended (never rewritten):

``decisions/<run_id>.jsonl`` -- written by the sidecar loop (Task 9), one line per
decision request it handled::

    {"id": "<run_id>-<seq:03>", "run_id": str, "kind": "shop"|"levelup"|"pivot"|"checkpoint",
     "screen": "shop"|"levelup"|"checkpoint", "character_id": str, "wave": int | null,
     "options": [request.options[] as the mod wrote them],
     "response": {validated Decision dict} | null,
     "source": "haiku" | "repair" | "fallback", "ts": ISO-8601 str}

``kind``, ``screen``, ``run_id`` and ``options`` are copied from the request file;
``character_id`` and ``wave`` from its state file. ``response`` is null when no valid
decision was produced (``source`` ``fallback``: the mod times out and its rules decide).
A line carrying ``decision`` instead of ``response`` is read the same way.

``decisions/experience.jsonl`` -- written at collect time (Task 10) from
``join_outcomes``, one record per decision::

    {"run_id", "kind", "character_id", "wave", "options", "action", "chosen", "source",
     "confidence", "outcome", "death_wave", "hp_next_wave", "kept_to_end"}

``action`` is the response's action (null without one). ``chosen`` is the option id for
an indexed action (buy/lock/pick), the action word otherwise, null without a response.
``hp_next_wave`` is the HP at the end of the wave after the decision's wave (0 when the
player died in it; null when the run never got there). ``kept_to_end`` is set for buys
only: whether the bought id is in the final build -- the ``death`` line's build, or the
last run-file line carrying a ``build`` (mod snapshots carry none today, so a won or
abandoned run gives null). A bought weapon counts as kept when any weapon of its family
(``weapon_smg_1`` -> ``weapon_smg_*``) is in the build, since two copies combine into
the next tier.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from brotato_bot.run.models import RunSummary

INDEXED_ACTIONS = frozenset({"buy", "lock", "pick"})
_TIER_SUFFIX = re.compile(r"_\d+$")


def append(path: Path, record: dict) -> None:
    """Append ``record`` as one JSON line (the parent directory is created). When the file
    does not end in a newline (a crash cut its last line short), a newline goes first so
    the new record never joins the broken line."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    with path.open("ab+") as fh:
        fh.seek(0, 2)
        if fh.tell() > 0:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                line = b"\n" + line
        fh.write(line)  # append mode: always written at the end
        fh.flush()


def read(path: Path) -> list[dict]:
    """Every JSON object line of ``path``; a missing file is empty and bad lines are skipped
    (a log may end in a half-written line after a crash)."""
    path = Path(path)
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_bytes().decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def query(path: Path, character_id: str, kind: str, n: int = 20) -> list[dict]:
    """The latest ``n`` records for ``character_id`` and ``kind``, oldest first."""
    if n <= 0:
        return []
    rows = [
        r for r in read(path) if r.get("character_id") == character_id and r.get("kind") == kind
    ]
    return rows[-n:]


def _family(item_id: str) -> str:
    return _TIER_SUFFIX.sub("", item_id) if item_id.startswith("weapon_") else item_id


def _final_build(summary: RunSummary, run_jsonl: Path | None) -> set[str] | None:
    if summary.death is not None:
        return {*summary.death.weapons, *summary.death.items}
    if run_jsonl is None:
        return None
    build: dict | None = None
    for e in read(run_jsonl):
        b = e.get("build")
        if e.get("kind") in ("snapshot", "death") and isinstance(b, dict):
            build = b
    if build is None:
        return None
    return {str(x) for key in ("weapons", "items") for x in build.get(key) or []}


def _kept(item_id: str, build: set[str] | None) -> bool | None:
    if build is None:
        return None
    if item_id in build:
        return True
    fam = _family(item_id)
    return fam != item_id and any(_family(b) == fam for b in build)


def _chosen_option(options: Any, index: Any) -> dict | None:
    if not isinstance(options, list) or not isinstance(index, int) or isinstance(index, bool):
        return None
    for opt in options:
        if isinstance(opt, dict) and opt.get("index") == index:
            return opt
    return None


def join_outcomes(
    decisions_jsonl: Path, run_summary: RunSummary, run_jsonl: Path | None = None
) -> list[dict]:
    """Experience records for ``run_summary``'s decisions in ``decisions_jsonl``.

    Lines whose ``run_id`` names another run are skipped. ``run_jsonl`` (the mod's run
    recording) is read only when the run has no death build, for a later line with one.
    """
    hp_end = {w.wave: (w.hp_end if w.completed else 0) for w in run_summary.waves}
    build: set[str] | None = None
    build_loaded = False
    out: list[dict] = []
    for rec in read(decisions_jsonl):
        rid = rec.get("run_id")
        if rid and rid != run_summary.run_id:
            continue
        resp = rec.get("response", rec.get("decision"))
        resp = resp if isinstance(resp, dict) else None
        action = resp.get("action") if resp else None
        options = rec.get("options") if isinstance(rec.get("options"), list) else []
        chosen: str | None = None
        kept: bool | None = None
        if action in INDEXED_ACTIONS:
            opt = _chosen_option(options, resp.get("option_index"))
            chosen = str(opt.get("id")) if opt and opt.get("id") else None
        elif isinstance(action, str):
            chosen = action
        if action == "buy" and chosen:
            if not build_loaded:
                build = _final_build(run_summary, run_jsonl)
                build_loaded = True
            kept = _kept(chosen, build)
        wave = rec.get("wave") if isinstance(rec.get("wave"), int) else None
        confidence = resp.get("confidence") if resp else None
        out.append(
            {
                "id": rec.get("id"),
                "run_id": run_summary.run_id,
                "kind": rec.get("kind"),
                "character_id": rec.get("character_id") or run_summary.character_id,
                "wave": wave,
                "options": options,
                "action": action,
                "chosen": chosen,
                "source": rec.get("source"),
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
                "outcome": run_summary.outcome,
                "death_wave": run_summary.death_wave,
                "hp_next_wave": hp_end.get(wave + 1) if wave is not None else None,
                "kept_to_end": kept,
            }
        )
    return out
