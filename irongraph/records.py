"""Personal-record engine.

Records are append-only per (exercise, record_type): the last element of a
history list is the current record; everything before it is preserved so
the full PR timeline is recoverable and auditable.

Record types (each only where the modality makes it meaningful):
  max_weight      heaviest successful set (lb-normalized; ties broken by reps)
  max_e1rm        best estimated 1RM (Epley, 1–12 reps)
  rep_weight:N    heaviest set at exactly N reps (kept for N in 1..12)
  max_reps        most reps in one unweighted set (bodyweight movements)
  max_added       heaviest added weight on a bodyweight movement
  max_volume      biggest single-session volume for the exercise
  max_duration    longest continuous effort (time / cardio)
  max_distance    longest distance in one session (cardio)
  best_pace       fastest pace, seconds per mile (cardio, ≥ 1 mile)

Different cardio modalities are never compared with each other — records
are always scoped to a single exercise id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import paths
from .analytics import epley_e1rm
from .models import SCHEMA_VERSION, WorkoutEntry, WorkoutEvent

MIN_PACE_DISTANCE_MI = 1.0


@dataclass
class PR:
    exercise_id: str
    exercise_name: str
    record_type: str
    value: float
    display: str            # human string, e.g. "185 lb × 6"
    previous_display: str | None
    delta_display: str | None
    date: str
    workout_id: str


def load_records() -> dict[str, Any]:
    p = paths.records_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"schema_version": SCHEMA_VERSION, "exercises": {}}


def save_records(rec: dict[str, Any]) -> None:
    p = paths.records_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")


def _current(rec: dict, ex_id: str, rtype: str) -> dict | None:
    hist = rec["exercises"].get(ex_id, {}).get(rtype)
    return hist[-1] if hist else None


def _push(rec: dict, ex_id: str, rtype: str, entry: dict) -> None:
    rec["exercises"].setdefault(ex_id, {}).setdefault(rtype, []).append(entry)


def _fmt_lb(v: float) -> str:
    return f"{v:g} lb" if abs(v - round(v)) < 0.05 else f"{v:.1f} lb"


def _fmt_dur(s: float) -> str:
    s = int(s)
    if s >= 3600:
        return f"{s // 3600}h {s % 3600 // 60}m"
    if s >= 60:
        return f"{s // 60}m {s % 60:02d}s" if s % 60 else f"{s // 60} min"
    return f"{s}s"


def _fmt_pace(spm: float) -> str:
    return f"{int(spm // 60)}:{int(spm % 60):02d} /mi"


def _candidates(entry: WorkoutEntry) -> list[tuple[str, float, str]]:
    """(record_type, value, display) candidates from one workout entry."""
    cands: list[tuple[str, float, str]] = []
    best_w = entry.best_weight_set()
    if best_w and best_w.weight_lb() is not None and not best_w.added_weight:
        w = best_w.weight_lb() or 0
        disp = _fmt_lb(w) + (f" × {best_w.reps}" if best_w.reps else "")
        cands.append(("max_weight", w, disp))
        if best_w.reps and 1 <= best_w.reps <= 12:
            cands.append((f"rep_weight:{best_w.reps}", w, disp))
    for s in entry.sets:
        sw = s.weight_lb()
        if sw is not None and s.reps and 1 <= s.reps <= 12 and not s.added_weight:
            e = epley_e1rm(sw, s.reps)
            if e:
                cands.append(("max_e1rm", round(e, 1), f"~{_fmt_lb(round(e))} e1RM ({_fmt_lb(sw)} × {s.reps})"))
            cands.append((f"rep_weight:{s.reps}", sw, _fmt_lb(sw) + f" × {s.reps}"))
        if s.added_weight and sw is not None:
            cands.append(("max_added", sw, f"+{_fmt_lb(sw)}" + (f" × {s.reps}" if s.reps else "")))
        if s.weight is None and s.reps and entry.modality == "reps":
            cands.append(("max_reps", float(s.reps), f"{s.reps} reps"))
    vol = entry.total_volume_lb()
    if vol > 0 and entry.modality in ("weight_reps", "weight_time"):
        cands.append(("max_volume", round(vol, 1), f"{_fmt_lb(round(vol))} session volume"))
    dur = entry.total_duration_s()
    if dur > 0 and entry.modality in ("time", "distance_time"):
        cands.append(("max_duration", dur, _fmt_dur(dur)))
    dist = entry.total_distance_mi()
    if dist > 0:
        cands.append(("max_distance", round(dist, 2), f"{dist:.2f} mi"))
        if dur and dist >= MIN_PACE_DISTANCE_MI:
            pace = dur / dist
            cands.append(("best_pace", round(pace, 1), _fmt_pace(pace)))
    # de-dup: keep best value per record type
    best: dict[str, tuple[str, float, str]] = {}
    for rtype, val, disp in cands:
        lower_is_better = rtype == "best_pace"
        cur = best.get(rtype)
        if cur is None or (val < cur[1] if lower_is_better else val > cur[1]):
            best[rtype] = (rtype, val, disp)
    return list(best.values())


def detect_and_apply_prs(event: WorkoutEvent, rec: dict[str, Any]) -> list[PR]:
    """Compare event against current records, append new PRs, return them."""
    prs: list[PR] = []
    for entry in event.entries:
        for rtype, val, disp in _candidates(entry):
            lower_is_better = rtype == "best_pace"
            cur = _current(rec, entry.exercise_id, rtype)
            is_pr = cur is None or (val < cur["value"] if lower_is_better else val > cur["value"])
            if not is_pr:
                continue
            delta = None
            if cur is not None:
                d = val - cur["value"]
                if rtype in ("max_weight", "max_e1rm", "max_added", "max_volume") or rtype.startswith("rep_weight"):
                    delta = f"+{_fmt_lb(abs(d))}"
                elif rtype == "max_reps":
                    delta = f"+{int(abs(d))} reps"
                elif rtype == "max_duration":
                    delta = f"+{_fmt_dur(abs(d))}"
                elif rtype == "max_distance":
                    delta = f"+{abs(d):.2f} mi"
                elif rtype == "best_pace":
                    delta = f"-{_fmt_dur(abs(d))}/mi"
            _push(rec, entry.exercise_id, rtype, {
                "value": val, "display": disp, "date": event.date, "workout_id": event.id,
            })
            prs.append(PR(
                exercise_id=entry.exercise_id, exercise_name=entry.exercise_name,
                record_type=rtype, value=val, display=disp,
                previous_display=cur["display"] if cur else None,
                delta_display=delta, date=event.date, workout_id=event.id,
            ))
    return prs


# Headline PRs shown in commit subjects / README: one per exercise, most
# meaningful type first. rep_weight PRs are interesting but noisy, so they
# only headline when nothing stronger fired for that exercise.
_HEADLINE_ORDER = ["max_weight", "max_e1rm", "max_added", "max_reps", "best_pace",
                   "max_distance", "max_duration", "max_volume"]


def headline_prs(prs: list[PR]) -> list[PR]:
    by_ex: dict[str, list[PR]] = {}
    for pr in prs:
        by_ex.setdefault(pr.exercise_id, []).append(pr)
    out = []
    for group in by_ex.values():
        def rank(p: PR) -> int:
            return _HEADLINE_ORDER.index(p.record_type) if p.record_type in _HEADLINE_ORDER else 99
        out.append(min(group, key=rank))
    return sorted(out, key=lambda p: p.exercise_name)
