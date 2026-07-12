"""Progression analytics: e1RM, trends, volume, frequency.

Estimated 1RM uses the Epley formula:  e1RM = w × (1 + reps/30)
Only applied for 1–12 reps; higher-rep sets make the estimate unreliable,
so they are excluded rather than reported with false precision.

Trend labels require `trend_min_sessions` distinct sessions (default 4);
anything less is "insufficient data" — one good day is not a trend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import paths
from .config import load_config
from .models import WorkoutEntry, WorkoutEvent


def epley_e1rm(weight_lb: float, reps: int, max_reps: int | None = None) -> float | None:
    cap = max_reps if max_reps is not None else load_config().e1rm_max_reps
    if reps < 1 or reps > cap:
        return None
    if reps == 1:
        return weight_lb
    return weight_lb * (1 + reps / 30.0)


def entry_best_e1rm(entry: WorkoutEntry) -> float | None:
    best = None
    for s in entry.sets:
        w = s.weight_lb()
        if w is None or s.reps is None or s.added_weight:
            continue
        e = epley_e1rm(w, s.reps)
        if e is not None and (best is None or e > best):
            best = e
    return best


def load_all_events() -> list[WorkoutEvent]:
    events = []
    root = paths.workouts_dir()
    if not root.exists():
        return []
    for f in sorted(root.rglob("*.json")):
        events.append(WorkoutEvent.from_dict(json.loads(f.read_text())))
    events.sort(key=lambda e: (e.date, e.id))
    return events


@dataclass
class ExerciseStats:
    exercise_id: str
    times_performed: int = 0
    last_performed: str | None = None
    first_performed: str | None = None
    total_volume_lb: float = 0.0
    total_duration_s: float = 0.0
    total_distance_mi: float = 0.0
    best_weight_lb: float | None = None
    best_weight_reps: int | None = None
    best_added_lb: float | None = None
    best_added_reps: int | None = None
    best_e1rm: float | None = None
    best_reps: int | None = None
    best_duration_s: float | None = None
    best_distance_mi: float | None = None
    best_pace_s_per_mi: float | None = None
    trend: str = "insufficient data"
    history: list[dict] | None = None  # per-session best snapshots


def session_snapshot(entry: WorkoutEntry, date: str) -> dict:
    snap: dict = {"date": date}
    # absolute-weight sets only; added-weight (bodyweight+) tracked separately
    abs_sets = [s for s in entry.sets if s.weight_lb() is not None and not s.added_weight]
    if abs_sets:
        bw = max(abs_sets, key=lambda s: (s.weight_lb() or 0, s.reps or 0))
        snap["weight_lb"] = round(bw.weight_lb() or 0, 1)
        snap["reps"] = bw.reps
        e = entry_best_e1rm(entry)
        if e:
            snap["e1rm_lb"] = round(e, 1)
    added = [s for s in entry.sets if s.added_weight and s.weight_lb() is not None]
    if added:
        best_add = max(added, key=lambda s: s.weight_lb() or 0)
        snap["added_lb"] = round(best_add.weight_lb() or 0, 1)
        snap["added_reps"] = best_add.reps
    br = entry.best_reps_set()
    if br and "reps" not in snap:
        snap["reps"] = br.reps
    vol = entry.total_volume_lb()
    if vol:
        snap["volume_lb"] = round(vol, 1)
    dur = entry.total_duration_s()
    if dur:
        snap["duration_s"] = round(dur)
    dist = entry.total_distance_mi()
    if dist:
        snap["distance_mi"] = round(dist, 2)
        if dur and dist > 0.05:
            snap["pace_s_per_mi"] = round(dur / dist)
    for s in entry.sets:
        if s.level is not None:
            snap["level"] = max(snap.get("level", 0), s.level)
    return snap


def _trend_from_history(hist: list[dict], min_sessions: int) -> str:
    key = None
    for k in ("e1rm_lb", "weight_lb", "reps", "distance_mi", "duration_s"):
        if sum(1 for h in hist if k in h) >= min_sessions:
            key = k
            break
    if key is None:
        return "insufficient data"
    vals = [h[key] for h in hist if key in h]
    recent = vals[-3:]
    prior = vals[-6:-3] or vals[:-3][-3:]
    if not prior:
        return "insufficient data"
    r, p = sum(recent) / len(recent), sum(prior) / len(prior)
    if p == 0:
        return "insufficient data"
    delta = (r - p) / abs(p)
    if delta > 0.02:
        return "improving"
    if delta < -0.02:
        return "declining"
    return "stable"


def compute_exercise_stats(events: list[WorkoutEvent]) -> dict[str, ExerciseStats]:
    cfg = load_config()
    out: dict[str, ExerciseStats] = {}
    for ev in events:
        for entry in ev.entries:
            st = out.setdefault(entry.exercise_id, ExerciseStats(exercise_id=entry.exercise_id, history=[]))
            st.times_performed += 1
            st.first_performed = st.first_performed or ev.date
            st.last_performed = ev.date
            st.total_volume_lb += entry.total_volume_lb()
            st.total_duration_s += entry.total_duration_s()
            st.total_distance_mi += entry.total_distance_mi()
            snap = session_snapshot(entry, ev.date)
            assert st.history is not None
            st.history.append(snap)
            w = snap.get("weight_lb")
            if w is not None and (st.best_weight_lb is None or w > st.best_weight_lb):
                st.best_weight_lb, st.best_weight_reps = w, snap.get("reps")
            aw = snap.get("added_lb")
            if aw is not None and (st.best_added_lb is None or aw > st.best_added_lb):
                st.best_added_lb, st.best_added_reps = aw, snap.get("added_reps")
            e = snap.get("e1rm_lb")
            if e is not None and (st.best_e1rm is None or e > st.best_e1rm):
                st.best_e1rm = e
            r = snap.get("reps")
            if r is not None and (st.best_reps is None or r > st.best_reps):
                st.best_reps = r
            d = snap.get("duration_s")
            if d is not None and (st.best_duration_s is None or d > st.best_duration_s):
                st.best_duration_s = d
            di = snap.get("distance_mi")
            if di is not None and (st.best_distance_mi is None or di > st.best_distance_mi):
                st.best_distance_mi = di
            pa = snap.get("pace_s_per_mi")
            if pa is not None and (st.best_pace_s_per_mi is None or pa < st.best_pace_s_per_mi):
                st.best_pace_s_per_mi = pa
    for st in out.values():
        st.trend = _trend_from_history(st.history or [], cfg.trend_min_sessions)
    return out


def muscle_distribution(events: list[WorkoutEvent], registry) -> dict[str, int]:
    """Count of entries touching each primary muscle group."""
    dist: dict[str, int] = {}
    for ev in events:
        for entry in ev.entries:
            ex = registry.by_id.get(entry.exercise_id)
            if not ex:
                continue
            for m in ex.primary_muscles:
                dist[m] = dist.get(m, 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: -kv[1]))
