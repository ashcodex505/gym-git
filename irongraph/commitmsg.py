"""Commit message generation.

Subject: conventional-commit style, ≤ 72 chars target, e.g.
  feat(workout): chest + back — 185 lb bench × 6, 160 lb pulldown × 8
Body: full workout detail, PRs, achievements, XP.

All user-supplied text is clamped and backtick-stripped by the parser
before it can reach this module; messages are passed to git via argv
(never through a shell string), so no interpolation risk.
"""

from __future__ import annotations

from datetime import date

from .achievements import AchievementDef
from .models import WorkoutEntry, WorkoutEvent
from .records import PR, _fmt_dur, headline_prs

SUBJECT_LIMIT = 72


def _entry_headline(e: WorkoutEntry) -> str | None:
    bw = e.best_weight_set()
    if bw and bw.weight_lb() is not None:
        w = bw.weight_lb() or 0
        short = _short_name(e.exercise_name)
        return f"{w:g} lb {short}" + (f" × {bw.reps}" if bw.reps else "")
    br = e.best_reps_set()
    if br and br.reps:
        return f"{_short_name(e.exercise_name)} × {br.reps}"
    d = e.total_distance_mi()
    if d:
        return f"{d:g} mi {_short_name(e.exercise_name)}"
    t = e.total_duration_s()
    if t:
        return f"{int(round(t / 60))} min {_short_name(e.exercise_name)}"
    return None


_SHORT = {
    "Barbell Bench Press": "bench", "Dumbbell Bench Press": "db bench",
    "Incline Bench Press": "incline", "Incline Dumbbell Press": "incline db",
    "Lat Pulldown": "pulldown", "Overhead Press": "ohp", "Back Squat": "squat",
    "Romanian Deadlift": "rdl", "Deadlift": "deadlift", "Barbell Row": "row",
    "Seated Cable Row": "cable row", "Pull-ups": "pull-ups", "Chin-ups": "chin-ups",
    "Treadmill": "treadmill", "Outdoor Run": "run", "StairMaster": "stairs",
    "Hanging Leg Raise": "leg raise", "Cable Crunch": "cable crunch",
}


def _short_name(name: str) -> str:
    return _SHORT.get(name, name.lower())


def _describe_entry(e: WorkoutEntry) -> str:
    parts = []
    if e.modality in ("weight_reps", "reps", "weight_time"):
        # group identical sets: "185 lb × 6 × 3 sets"
        groups: list[tuple[str, int]] = []
        for s in e.sets:
            desc = ""
            if s.weight is not None:
                unit = s.unit or "lb"
                prefix = "+" if s.added_weight else ""
                desc = f"{prefix}{s.weight:g} {unit}"
            elif e.modality == "reps":
                desc = "bw"
            if s.reps is not None:
                desc = f"{desc} × {s.reps}" if desc else f"{s.reps} reps"
            if s.duration_s:
                desc = (desc + " " if desc else "") + _fmt_dur(s.duration_s)
            if groups and groups[-1][0] == desc:
                groups[-1] = (desc, groups[-1][1] + 1)
            else:
                groups.append((desc, 1))
        parts = [d + (f" × {n} sets" if n > 1 else "") for d, n in groups]
    else:
        c = e.sets[0] if e.sets else None
        if c:
            if c.duration_s:
                parts.append(_fmt_dur(c.duration_s))
            if c.distance is not None:
                parts.append(f"{c.distance:g} {c.distance_unit or 'mi'}")
            if c.incline_pct is not None:
                parts.append(f"incline {c.incline_pct:g}%")
            if c.speed is not None:
                parts.append(f"speed {c.speed:g} mph")
            if c.level is not None:
                parts.append(f"level {c.level}")
            if c.calories is not None:
                parts.append(f"{c.calories:g} cal")
    line = f"- {e.exercise_name}: " + (", ".join(parts) if parts else "completed")
    if e.notes:
        line += f"  ({e.notes})"
    return line


def build_subject(event: WorkoutEvent, prs: list[PR]) -> str:
    wtype = event.workout_type
    heads = headline_prs(prs)
    highlights: list[str] = []
    pr_ex = {p.exercise_id for p in heads}
    ordered = sorted(event.entries, key=lambda e: (e.exercise_id not in pr_ex,))
    for e in ordered:
        h = _entry_headline(e)
        if h:
            highlights.append(h)
    subject = f"feat(workout): {wtype}"
    for i, h in enumerate(highlights):
        cand = subject + (" — " if i == 0 else ", ") + h
        if len(cand) > SUBJECT_LIMIT:
            break
        subject = cand
    return subject


def build_body(event: WorkoutEvent, prs: list[PR], new_achievements: list[AchievementDef],
               xp_grants: dict[str, int], author_name: str, author_email: str,
               streak_line: str | None = None) -> str:
    d = date.fromisoformat(event.date).strftime("%B %-d, %Y")
    lines = [f"Workout completed on {d}", ""]
    strength = [e for e in event.entries if e.modality in ("weight_reps", "reps", "weight_time")]
    cardio = [e for e in event.entries if e.modality in ("time", "distance_time")]
    if strength:
        lines.append("Strength:")
        lines += [_describe_entry(e) for e in strength]
        lines.append("")
    if cardio:
        lines.append("Cardio & conditioning:")
        lines += [_describe_entry(e) for e in cardio]
        lines.append("")
    progress = []
    for pr in headline_prs(prs):
        line = f"- 🏆 New {pr.exercise_name} PR: {pr.display}"
        if pr.delta_display:
            line += f" ({pr.delta_display} vs previous {pr.previous_display})"
        progress.append(line)
    extra = [p for p in prs if p not in headline_prs(prs)]
    if extra:
        progress.append(f"- 📈 {len(extra)} additional record{'s' if len(extra) != 1 else ''} improved")
    for a in new_achievements:
        progress.append(f"- {a.emoji} Achievement unlocked: {a.name} — {a.description}")
    if streak_line:
        progress.append(f"- 🔥 {streak_line}")
    progress.append(f"- ⚔️ {len(event.entries)} exercise{'s' if len(event.entries) != 1 else ''} completed, +{sum(xp_grants.values())} XP")
    if progress:
        lines.append("Progress:")
        lines += progress
        lines.append("")
    if event.notes:
        lines.append(f"Notes: {event.notes}")
        lines.append("")
    lines.append("Recorded automatically by IronGraph (github.com actions).")
    lines.append(f"Author: {author_name} <{author_email}>")
    lines.append(f"Workout-Id: {event.id}")
    return "\n".join(lines)
