"""Achievement engine.

Achievements are declarative: (id, name, emoji, description, predicate).
Predicates receive a Context and must be deterministic and recomputable
from history — no hidden state. Unlocks are append-only in
data/achievements.json.

Deliberately not barbell-centric: cardio, calisthenics, core, and
consistency all have first-class achievements.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import paths
from .models import SCHEMA_VERSION, WorkoutEvent
from .records import PR
from .streaks import Streaks


@dataclass
class Context:
    event: WorkoutEvent
    events: list[WorkoutEvent]           # full history including event
    prs: list[PR]                        # PRs fired by this event
    all_pr_count: int                    # total PRs ever (after this event)
    streaks: Streaks
    exercise_ids_ever: set[str] = field(default_factory=set)
    movement_patterns_ever: set[str] = field(default_factory=set)
    stats: dict[str, Any] = field(default_factory=dict)   # exercise stats by id


def _bench_lb(ctx: Context) -> float:
    st = ctx.stats.get("barbell-bench-press")
    return (st.best_weight_lb or 0) if st else 0


def _squat_lb(ctx: Context) -> float:
    st = ctx.stats.get("back-squat")
    return (st.best_weight_lb or 0) if st else 0


def _deadlift_lb(ctx: Context) -> float:
    st = ctx.stats.get("deadlift")
    return (st.best_weight_lb or 0) if st else 0


def _total_distance(ctx: Context, ex_id: str) -> float:
    st = ctx.stats.get(ex_id)
    return st.total_distance_mi if st else 0


def _any_session_distance_at_least(ctx: Context, mi: float) -> bool:
    for ev in ctx.events:
        for e in ev.entries:
            if e.total_distance_mi() >= mi:
                return True
    return False


def _cardio_entries(ctx: Context) -> int:
    n = 0
    for ev in ctx.events:
        for e in ev.entries:
            if e.modality in ("time", "distance_time") and (e.total_duration_s() or e.total_distance_mi()):
                n += 1
    return n


@dataclass(frozen=True)
class AchievementDef:
    id: str
    name: str
    emoji: str
    description: str
    predicate: Callable[[Context], bool]
    hidden: bool = False


ACHIEVEMENTS: list[AchievementDef] = [
    AchievementDef("first-commit", "First Commit", "🏁",
                   "Complete your first recorded workout.",
                   lambda c: len(c.events) >= 1),
    AchievementDef("ten-workouts", "Double Digits", "🔟",
                   "Complete 10 recorded workouts.",
                   lambda c: len(c.events) >= 10),
    AchievementDef("fifty-workouts", "Half Century", "🏗️",
                   "Complete 50 recorded workouts.",
                   lambda c: len(c.events) >= 50),
    AchievementDef("hundred-workouts", "Century of Iron", "💯",
                   "Complete 100 recorded workouts.",
                   lambda c: len(c.events) >= 100),
    AchievementDef("first-pr", "Breaking Ground", "📈",
                   "Set your first personal record.",
                   lambda c: c.all_pr_count >= 1),
    AchievementDef("pr-machine", "PR Machine", "🏆",
                   "Set 10 personal records.",
                   lambda c: c.all_pr_count >= 10),
    AchievementDef("pr-factory", "PR Factory", "⚙️",
                   "Set 50 personal records.",
                   lambda c: c.all_pr_count >= 50),
    AchievementDef("progressive-overload", "Progressive Overload", "⚔️",
                   "Improve the same exercise three separate times.",
                   lambda c: any(
                       len([h for h in (st.history or []) if "weight_lb" in h or "reps" in h]) >= 4
                       and st.trend == "improving"
                       for st in c.stats.values())),
    AchievementDef("one-plate-bench", "One Plate Club", "🧱",
                   "Bench press 135 lb.", lambda c: _bench_lb(c) >= 135),
    AchievementDef("two-plate-bench", "Two Plate Club", "⚒️",
                   "Bench press 225 lb.", lambda c: _bench_lb(c) >= 225),
    AchievementDef("three-plate-squat", "Three Plate Squat", "🏛️",
                   "Squat 315 lb.", lambda c: _squat_lb(c) >= 315),
    AchievementDef("four-plate-pull", "Four Plate Pull", "🌋",
                   "Deadlift 405 lb.", lambda c: _deadlift_lb(c) >= 405),
    AchievementDef("explorer", "Explorer", "🌌",
                   "Perform exercises from 10 different movement families.",
                   lambda c: len(c.movement_patterns_ever) >= 10),
    AchievementDef("polymath", "Polymath", "🗺️",
                   "Perform 25 different exercises.",
                   lambda c: len(c.exercise_ids_ever) >= 25),
    AchievementDef("seven-day-flame", "Seven-Day Flame", "🔥",
                   "Log activity on seven consecutive days.",
                   lambda c: c.streaks.activity_longest >= 7),
    AchievementDef("steady-forge", "Steady Forge", "🔩",
                   "Hit your weekly workout target four weeks in a row.",
                   lambda c: c.streaks.weekly_longest >= 4),
    AchievementDef("quarter-of-iron", "Quarter of Iron", "🗓️",
                   "Hit your weekly workout target twelve weeks in a row.",
                   lambda c: c.streaks.weekly_longest >= 12),
    AchievementDef("first-5k", "First 5K", "🏅",
                   "Cover 3.11 miles in a single cardio session.",
                   lambda c: _any_session_distance_at_least(c, 3.11)),
    AchievementDef("marathon-month", "Marathon Month", "🌙",
                   "Accumulate 26.2 miles of cardio in one calendar month.",
                   lambda c: _marathon_month(c)),
    AchievementDef("cardio-regular", "Engine Builder", "❤️",
                   "Complete 20 cardio sessions.",
                   lambda c: _cardio_entries(c) >= 20),
    AchievementDef("bodyweight-master", "Gravity Is Optional", "🕊️",
                   "Perform 10 or more reps of a weighted bodyweight movement.",
                   lambda c: any(
                       s.added_weight and (s.reps or 0) >= 10
                       for ev in c.events for e in ev.entries for s in e.sets)),
    AchievementDef("iron-core", "Iron Core", "🧿",
                   "Hold a plank for 3 minutes.",
                   lambda c: any(
                       e.exercise_id == "plank" and e.total_duration_s() >= 180
                       for ev in c.events for e in ev.entries)),
    AchievementDef("comeback", "The Comeback", "🌅",
                   "Return to training after 14+ days away.",
                   lambda c: _comeback(c)),
]


def _marathon_month(ctx: Context) -> bool:
    per_month: dict[str, float] = {}
    for ev in ctx.events:
        month = ev.date[:7]
        for e in ev.entries:
            per_month[month] = per_month.get(month, 0) + e.total_distance_mi()
    return any(v >= 26.2 for v in per_month.values())


def _comeback(ctx: Context) -> bool:
    from datetime import date
    days = sorted({date.fromisoformat(ev.date) for ev in ctx.events})
    return any((b - a).days >= 14 for a, b in zip(days, days[1:]))


def load_unlocked() -> dict[str, Any]:
    p = paths.achievements_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"schema_version": SCHEMA_VERSION, "unlocked": []}


def save_unlocked(data: dict[str, Any]) -> None:
    p = paths.achievements_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def evaluate(ctx: Context, unlocked_data: dict[str, Any]) -> list[AchievementDef]:
    """Returns newly unlocked achievements and appends them to unlocked_data."""
    have = {u["id"] for u in unlocked_data["unlocked"]}
    new: list[AchievementDef] = []
    for a in ACHIEVEMENTS:
        if a.id in have:
            continue
        try:
            if a.predicate(ctx):
                unlocked_data["unlocked"].append({
                    "id": a.id, "name": a.name, "emoji": a.emoji,
                    "description": a.description,
                    "date": ctx.event.date, "workout_id": ctx.event.id,
                })
                new.append(a)
        except Exception:
            continue  # a broken predicate must never block ingestion
    return new
