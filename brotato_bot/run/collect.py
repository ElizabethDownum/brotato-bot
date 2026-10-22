"""Turn the mod's run recording (``runs/<run_id>.jsonl``) into a summary, a markdown
report and a ``runs/index.json`` row.

Event shapes are the mod's as built (runbook section 4; ``core/run_recorder.gd``,
``extensions/main.gd``, ``bot_runtime.gd``, the shop and upgrades extensions). Every line
is ``{"t": ms, "kind": ..., ...data}``. Unknown kinds (e.g. ``bot_state``) are ignored so
later mod versions can add events, and every field is optional: older recordings without
``shop`` events or ``wave`` on ``decision``/``levelup`` still collect. The shop ledger
comes from ``shop`` events (one per shop action) when the recording has any, else from
``decision_applied`` lines, the only shop record in recordings made before ``shop`` existed.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from brotato_bot.fsutil import atomic_write_json, atomic_write_text, plain_name, read_json
from brotato_bot.paths import Paths
from brotato_bot.report import render
from brotato_bot.run.models import (
    CheckpointRow,
    DeathRecord,
    DecisionRow,
    LevelupRow,
    RunSummary,
    ShopRow,
    WaveRow,
)
from brotato_bot.sidecar import experience

END_OUTCOMES = {"won": "win", "death": "death"}  # abandoned / quit / no end line: incomplete


def parse_jsonl(path: Path) -> list[dict]:
    """Every JSON object line of ``path``. A final line that does not parse (a crash
    mid-write) is skipped; an unparsable line anywhere else raises ValueError."""
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    lines = [(n, line) for n, line in enumerate(text.splitlines(), 1) if line.strip()]
    out: list[dict] = []
    for i, (n, line) in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            if i == len(lines) - 1:
                break
            raise ValueError(f"{path} line {n}: {exc}") from exc
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def _float(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def _option(request: dict | None, index: int | None) -> dict | None:
    if request is None or index is None:
        return None
    options = request.get("options")
    if not isinstance(options, list):
        return None
    for opt in options:
        if isinstance(opt, dict) and _int(opt.get("index")) == index:
            return opt
    return None


def summarize(events: list[dict], requests: dict[str, dict] | None = None) -> RunSummary:
    """Fold the run's events into a RunSummary. ``requests`` maps decision id to the
    mod's request file, used to name the item, price and score behind a shop action."""
    requests = requests or {}
    header: dict = next((e for e in events if e.get("kind") == "header"), {})
    waves: dict[int, WaveRow] = {}
    shop: list[ShopRow] = []
    applied_rows: list[ShopRow] = []  # from decision_applied: the ledger for older recordings
    levelups: list[LevelupRow] = []
    decisions: list[DecisionRow] = []
    by_id: dict[str, DecisionRow] = {}
    checkpoints: list[CheckpointRow] = []
    challenges: list[str] = []
    targets: list[str] = []
    notes: list[str] = []
    death: DeathRecord | None = None
    end: dict | None = None
    complete: dict | None = None
    last_wave: int | None = None  # the last wave that ended: shops and level-ups follow it

    for e in events:
        kind = e.get("kind")
        if kind == "wave_end":
            w = _int(e.get("wave"))
            if w is None:
                continue
            waves[w] = WaveRow(
                wave=w,
                hp_end=_int(e.get("hp")),
                gold_end=_int(e.get("gold")),
                damage_taken=_int(e.get("damage_taken")),
                kills=_int(e.get("kills")),
            )
            last_wave = w
        elif kind == "decision":
            resp = e.get("response") if isinstance(e.get("response"), dict) else {}
            wave = _int(e.get("wave"))
            row = DecisionRow(
                wave=wave if wave is not None else last_wave,
                id=_str(e.get("id")) or "",
                kind=_str(e.get("request_kind")) or "?",
                source=_str(e.get("source")) or "?",
                action=_str(resp.get("action")),
                option_index=_int(resp.get("option_index")),
                confidence=_float(resp.get("confidence")),
                rationale=_str(resp.get("rationale")),
            )
            decisions.append(row)
            if row.id:
                by_id[row.id] = row
        elif kind == "decision_applied":
            did = _str(e.get("id")) or ""
            dec = by_id.get(did)
            applied = _str(e.get("applied")) or "?"
            idx = _int(e.get("option_index"))
            opt = _option(requests.get(did), idx) if applied in ("buy", "lock") else None
            applied_rows.append(
                ShopRow(
                    wave=dec.wave if dec else last_wave,
                    id=did,
                    action=applied,
                    option_index=idx,
                    item=_str(opt.get("id")) if opt else None,
                    price=_int(opt.get("price")) if opt else None,
                    score=_float(opt.get("score")) if opt else None,
                    source=dec.source if dec else None,
                )
            )
        elif kind == "shop":
            wave = _int(e.get("wave"))
            shop.append(
                ShopRow(
                    wave=wave if wave is not None else last_wave,
                    action=_str(e.get("action")) or "?",
                    item=_str(e.get("item_id")),
                    price=_int(e.get("price")),
                    score=_float(e.get("score")),
                    source=_str(e.get("source")),
                    gold_after=_int(e.get("gold_after")),
                )
            )
        elif kind == "levelup":
            picked = _str(e.get("picked")) or "?"
            alts = [a for a in e.get("alternatives") or [] if isinstance(a, dict)]
            score = next((_float(a.get("score")) for a in alts if a.get("id") == picked), None)
            wave = _int(e.get("wave"))
            levelups.append(
                LevelupRow(
                    wave=wave if wave is not None else last_wave,
                    id=_str(e.get("id")),
                    picked=picked,
                    source=_str(e.get("source")) or "?",
                    alternatives=[str(a.get("id", "")) for a in alts if a.get("id") != picked],
                    score=score,
                )
            )
        elif kind == "checkpoint":
            checkpoints.append(
                CheckpointRow(
                    wave=last_wave,
                    id=_str(e.get("id")) or "",
                    action=_str(e.get("action")),
                    applied=_str(e.get("applied")) or "?",
                    reason=_str(e.get("reason")) or "",
                )
            )
        elif kind == "challenge":
            cid = _str(e.get("id")) or ""
            if cid and cid not in challenges:
                challenges.append(cid)
            if cid and e.get("is_target") is True and cid not in targets:
                targets.append(cid)
        elif kind == "death":
            if death is None:
                build = e.get("build") if isinstance(e.get("build"), dict) else {}
                death = DeathRecord(
                    wave=_int(e.get("wave")) or 0,
                    killer=_str(e.get("killer")) or "",
                    last_threats=[str(t) for t in e.get("last_threats") or []],
                    weapons=[str(x) for x in build.get("weapons") or []],
                    items=[str(x) for x in build.get("items") or []],
                    dmg_w=_int(e.get("dmg_w")),
                    position=e.get("position"),
                )
        elif kind == "warning":
            text = _str(e.get("reason")) or _str(e.get("message")) or ""
            notes.append(f"warning: {text}")
        elif kind == "halt":
            notes.append(f"halted: {e.get('reason', '')}")
        elif kind == "complete":
            complete = e
        elif kind == "end":
            end = e

    end_word = _str(end.get("outcome")) if end else None
    outcome = END_OUTCOMES.get(end_word or "", "incomplete")
    if end is None:
        notes.append("no end line: the recording stops early (crash or still running)")
    if complete is None and end is not None and outcome != "incomplete":
        notes.append("no complete line: the bot was not playing when the run ended")

    death_wave: int | None = None
    if outcome == "death":
        death_wave = death.wave if death and death.wave else _int(end.get("wave") if end else None)
    if death is not None and death.wave and death.wave not in waves:
        waves[death.wave] = WaveRow(
            wave=death.wave,
            hp_end=0,
            gold_end=_int(end.get("gold")) if end and outcome == "death" else None,
            damage_taken=death.dmg_w,
            completed=False,
        )

    start_wave = _int(header.get("start_wave")) or 1
    if start_wave > 1:
        notes.append(f"recording starts at wave {start_wave} (resumed or retried run)")

    return RunSummary(
        run_id=_str(header.get("run_id")) or "",
        character_id=_str(header.get("character_id")) or "",
        danger=_int(header.get("danger")),
        plan_id=_str(header.get("plan_id")) or "",
        start_wave=start_wave,
        target_challenge=targets[0] if targets else None,
        outcome=outcome,
        end_outcome=end_word,
        death_wave=death_wave,
        waves=[waves[k] for k in sorted(waves)],
        shop=shop or applied_rows,
        levelups=levelups,
        decisions=decisions,
        checkpoints=checkpoints,
        challenges=challenges,
        targets_completed=targets,
        death=death,
        notes=notes,
    )


def _load_requests(events: list[dict], requests_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in events:
        did = e.get("id") if e.get("kind") == "decision" else None
        if not isinstance(did, str) or not did or did in out:
            continue
        try:
            f = requests_dir / f"{plain_name(did)}.json"
        except ValueError:
            continue  # an id that is not a plain name never leaves requests_dir
        try:
            req = read_json(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(req, dict):
            out[did] = req
    return out


def _read_target(path: Path, plan_id: str | None = None) -> str | None:
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if plan_id is not None and data.get("plan_id") != plan_id:
        return None
    t = data.get("target_challenge")
    return t if isinstance(t, str) and t else None


def resolve_target(summary: RunSummary, paths: Paths) -> str | None:
    """The run's target: a challenge the mod flagged ``is_target``, else the plan file's
    non-empty target (when it is this run's plan), else config.json's, else None. The
    files are read at collect time, so they reflect the latest ``prepare``."""
    if summary.targets_completed:
        return summary.targets_completed[0]
    return _read_target(paths.plan_json, summary.plan_id) or _read_target(paths.config_json)


def latest_run_id(paths: Paths) -> str | None:
    runs = sorted(paths.runs_in.glob("*.jsonl"), key=lambda f: (f.stat().st_mtime, f.name))
    return runs[-1].stem if runs else None


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=dst.name + ".", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def index_row(summary: RunSummary) -> dict:
    """The ``runs/index.json`` row. Plan 3's stagnation check reads exactly these keys."""
    return {
        "run_id": summary.run_id,
        "character_id": summary.character_id,
        "danger": summary.danger,
        "plan_id": summary.plan_id,
        "target_challenge": summary.target_challenge,
        "outcome": summary.outcome,
        "death_wave": summary.death_wave,
        "hp_end_last_wave": summary.hp_end_last_wave,
        "proposal_n": None,
    }


def append_index(index_path: Path, row: dict) -> None:
    """Append ``row`` to the JSON list at ``index_path`` (created as ``[]``). A row with
    the same run_id (a re-collect) is replaced in place; other rows are left as they are."""
    rows = read_json(index_path) if index_path.is_file() else []
    if not isinstance(rows, list):
        raise ValueError(f"{index_path} is not a JSON list")  # noqa: TRY004 (bad file content)
    for i, r in enumerate(rows):
        if isinstance(r, dict) and r.get("run_id") == row["run_id"]:
            rows[i] = row
            break
    else:
        rows.append(row)
    atomic_write_json(index_path, rows)


def collect(run_id: str, paths: Paths) -> Path:
    """Summarize ``<runs_in>/<run_id>.jsonl``; write ``<runs_out>/<run_id>.md``, copy the
    JSONL beside it and update ``<runs_out>/index.json``. Returns the report path.

    ``run_id`` must be a plain file name (ValueError otherwise). It names every file and
    the index row; a header run_id that disagrees is reported as a note."""
    plain_name(run_id)
    src = paths.runs_in / f"{run_id}.jsonl"
    if not src.is_file():
        raise FileNotFoundError(f"no run recording at {src}")
    events = parse_jsonl(src)
    summary = summarize(events, _load_requests(events, paths.requests_dir))
    if summary.run_id and summary.run_id != run_id:
        summary.notes.append(
            f"warning: header run_id {summary.run_id!r} differs from the file name {run_id!r}"
        )
    summary.run_id = run_id
    summary.target_challenge = resolve_target(summary, paths)

    outcomes: dict[str, str] = {}
    decisions_path = paths.decisions_dir / f"{run_id}.jsonl"
    if decisions_path.is_file():
        experience_path = paths.decisions_dir / "experience.jsonl"
        seen = {(rec.get("run_id"), rec.get("id")) for rec in experience.read(experience_path)}
        for record in experience.join_outcomes(decisions_path, summary, run_jsonl=src):
            if record["id"]:
                outcomes[record["id"]] = record["outcome"]
            key = (record["run_id"], record["id"])
            if key not in seen:
                experience.append(experience_path, record)
                seen.add(key)

    out_dir = paths.runs_out
    _atomic_copy(src, out_dir / f"{run_id}.jsonl")
    report = out_dir / f"{run_id}.md"
    atomic_write_text(report, render.run_report(summary, outcomes))
    append_index(out_dir / "index.json", index_row(summary))
    return report
