"""Central configuration loader (config/irongraph.yml)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from . import paths

DEFAULTS: dict[str, Any] = {
    "git_author": {"name": "Ashish Kurse", "email": "ashishkurse@gmail.com"},
    "timezone": "America/Phoenix",
    "default_weight_unit": "lb",
    "default_distance_unit": "mi",
    "privacy": {"publish_bodyweight": False, "publish_notes": True},
    "e1rm_formula": "epley",
    "e1rm_max_reps": 12,
    "trend_min_sessions": 4,
    "xp": {
        "workout_complete": 50,
        "per_exercise": 10,
        "per_exercise_cap": 8,
        "personal_record": 75,
        "new_exercise": 25,
        "weekly_streak_bonus": 40,
    },
    "weekly_consistency_target": 3,
}


@dataclass(frozen=True)
class GitAuthor:
    name: str
    email: str


@dataclass(frozen=True)
class Config:
    git_author: GitAuthor
    timezone: str
    default_weight_unit: str
    default_distance_unit: str
    privacy: dict[str, bool]
    e1rm_max_reps: int
    trend_min_sessions: int
    xp: dict[str, int]
    weekly_consistency_target: int
    raw: dict[str, Any] = field(default_factory=dict)


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


@lru_cache(maxsize=1)
def load_config() -> Config:
    raw: dict[str, Any] = {}
    p = paths.config_path()
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
    merged = _merge(DEFAULTS, raw)
    return Config(
        git_author=GitAuthor(**merged["git_author"]),
        timezone=merged["timezone"],
        default_weight_unit=merged["default_weight_unit"],
        default_distance_unit=merged["default_distance_unit"],
        privacy=merged["privacy"],
        e1rm_max_reps=int(merged["e1rm_max_reps"]),
        trend_min_sessions=int(merged["trend_min_sessions"]),
        xp={k: int(v) for k, v in merged["xp"].items()},
        weekly_consistency_target=int(merged["weekly_consistency_target"]),
        raw=merged,
    )
