"""XP, levels, and profile state.

XP sources (values from config/irongraph.yml):
  +50  completing a workout
  +10  per exercise, capped at 8 per workout (junk volume earns nothing)
  +75  per personal record
  +25  first time ever performing an exercise
  +40  each newly completed weekly-consistency week

Level curve: cumulative XP needed for level n is 250·n·(n+1)/2 — i.e. each
level costs 250·level more than the last. Documented, deterministic,
recomputable from history.
"""

from __future__ import annotations

import json
from typing import Any

from . import paths
from .config import load_config
from .models import SCHEMA_VERSION

LEVEL_TITLES = [
    (1, "Novice"), (3, "Initiate"), (5, "Apprentice"), (8, "Journeyman"),
    (10, "Ironbound"), (14, "Sentinel"), (18, "Vanguard"), (22, "Warden"),
    (26, "Colossus"), (30, "Titan"), (40, "Mythic"), (50, "Paragon"),
]


def xp_for_level(level: int) -> int:
    """Total XP required to *reach* `level` (level 1 = 0 XP)."""
    n = level - 1
    return 250 * n * (n + 1) // 2


def level_from_xp(xp: int) -> int:
    lvl = 1
    while xp_for_level(lvl + 1) <= xp:
        lvl += 1
    return lvl


def title_for_level(level: int) -> str:
    title = LEVEL_TITLES[0][1]
    for lv, t in LEVEL_TITLES:
        if level >= lv:
            title = t
    return title


def default_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "xp": 0, "level": 1, "title": "Novice",
        "totals": {"workouts": 0, "prs": 0, "exercises_tried": 0},
        "xp_log": [],   # append-only audit of every XP grant
        "streaks": {},
    }


def load_profile() -> dict[str, Any]:
    p = paths.profile_path()
    if p.exists():
        return json.loads(p.read_text())
    return default_profile()


def save_profile(prof: dict[str, Any]) -> None:
    p = paths.profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prof, indent=2) + "\n")


def award_xp(prof: dict[str, Any], *, workout_id: str, n_exercises: int,
             n_prs: int, n_new_exercises: int, new_streak_weeks: int) -> dict[str, int]:
    cfg = load_config().xp
    grants = {
        "workout": cfg["workout_complete"],
        "exercises": min(n_exercises, cfg["per_exercise_cap"]) * cfg["per_exercise"],
        "prs": n_prs * cfg["personal_record"],
        "new_exercises": n_new_exercises * cfg["new_exercise"],
        "streak": new_streak_weeks * cfg["weekly_streak_bonus"],
    }
    total = sum(grants.values())
    prof["xp"] += total
    prof["level"] = level_from_xp(prof["xp"])
    prof["title"] = title_for_level(prof["level"])
    prof["xp_log"].append({"workout_id": workout_id, "grants": grants, "total": total})
    return grants
