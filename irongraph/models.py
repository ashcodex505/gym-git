"""Canonical domain models.

Design notes
------------
* One `WorkoutEvent` per completed daily quest. Events are append-only:
  a file under data/workouts/YYYY/ is never rewritten after ingestion.
* A `SetRecord` is deliberately sparse — different modalities populate
  different fields. Nothing forces a weight onto a plank or a distance
  onto a bench press.
* Weights are stored in the unit the user entered (auditable), with kg/lb
  conversion done at comparison time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 1

Modality = Literal["weight_reps", "reps", "time", "distance_time", "weight_time"]

LB_PER_KG = 2.2046226218

MUSCLE_GROUPS = [
    "chest", "upper-chest", "lower-chest", "lats", "mid-back", "lower-back", "traps",
    "front-delts", "side-delts", "rear-delts", "biceps", "triceps", "forearms",
    "quads", "hamstrings", "glutes", "calves", "abs", "obliques", "core",
    "hip-flexors", "legs", "full-body", "cardiovascular", "upper-back",
]

CATEGORIES = [
    "chest", "back", "shoulders", "biceps", "triceps", "legs", "glutes",
    "core", "cardio", "calisthenics", "mobility", "other",
]


def to_lb(value: float, unit: str) -> float:
    return value * LB_PER_KG if unit == "kg" else value


@dataclass
class Exercise:
    id: str
    name: str
    category: str
    primary_muscles: list[str]
    secondary_muscles: list[str] = field(default_factory=list)
    movement_pattern: str = "other"
    equipment: str = "other"
    modality: Modality = "weight_reps"
    compound: bool = False
    aliases: list[str] = field(default_factory=list)
    supports_added_weight: bool = False
    supports_level: bool = False
    custom: bool = False
    instructions: str = ""
    relations: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Exercise:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "aliases": self.aliases,
            "category": self.category, "primary_muscles": self.primary_muscles,
            "secondary_muscles": self.secondary_muscles,
            "movement_pattern": self.movement_pattern, "equipment": self.equipment,
            "modality": self.modality, "compound": self.compound,
            "supports_added_weight": self.supports_added_weight,
            "supports_level": self.supports_level, "custom": self.custom,
            "instructions": self.instructions, "relations": self.relations,
        }


@dataclass
class SetRecord:
    """One performed set (or one continuous cardio effort)."""
    weight: float | None = None          # numeric weight; None for pure bodyweight
    unit: str | None = None              # lb | kg
    added_weight: bool = False           # True => weight was added to bodyweight
    reps: int | None = None
    duration_s: float | None = None
    distance: float | None = None
    distance_unit: str | None = None     # mi | km | m
    incline_pct: float | None = None
    speed: float | None = None           # mph (treadmill speed setting)
    level: int | None = None
    calories: float | None = None
    rpe: float | None = None
    distance_derived: bool = False       # True when computed from speed × time

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, False)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SetRecord:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def weight_lb(self) -> float | None:
        if self.weight is None:
            return None
        return to_lb(self.weight, self.unit or "lb")

    def distance_mi(self) -> float | None:
        if self.distance is None:
            return None
        u = self.distance_unit or "mi"
        if u == "km":
            return self.distance * 0.6213712
        if u == "m":
            return self.distance * 0.0006213712
        return self.distance

    def pace_s_per_mi(self) -> float | None:
        d = self.distance_mi()
        if d and self.duration_s and d > 0.05:
            return self.duration_s / d
        return None


@dataclass
class WorkoutEntry:
    """All work performed on one exercise within one workout."""
    exercise_id: str
    exercise_name: str
    modality: Modality
    sets: list[SetRecord] = field(default_factory=list)
    notes: str | None = None
    raw: str = ""                        # original issue text, kept for audit

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "modality": self.modality,
            "sets": [s.to_dict() for s in self.sets],
            "raw": self.raw,
        }
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkoutEntry:
        return cls(
            exercise_id=d["exercise_id"], exercise_name=d["exercise_name"],
            modality=d["modality"],
            sets=[SetRecord.from_dict(s) for s in d.get("sets", [])],
            notes=d.get("notes"), raw=d.get("raw", ""),
        )

    # --- best-performance helpers -------------------------------------
    def best_weight_set(self) -> SetRecord | None:
        cands = [s for s in self.sets if s.weight_lb() is not None]
        return max(cands, key=lambda s: (s.weight_lb() or 0, s.reps or 0), default=None)

    def best_reps_set(self) -> SetRecord | None:
        cands = [s for s in self.sets if s.reps is not None]
        return max(cands, key=lambda s: s.reps or 0, default=None)

    def total_volume_lb(self) -> float:
        return sum((s.weight_lb() or 0) * (s.reps or 0) for s in self.sets)

    def total_duration_s(self) -> float:
        return sum(s.duration_s or 0 for s in self.sets)

    def total_distance_mi(self) -> float:
        return sum(s.distance_mi() or 0 for s in self.sets)


@dataclass
class WorkoutEvent:
    id: str                              # durable ingestion key, e.g. "issue-42"
    date: str                            # YYYY-MM-DD, local (America/Phoenix)
    entries: list[WorkoutEntry]
    source: dict[str, Any] = field(default_factory=dict)
    logged_at: str = ""                  # ISO timestamp of ingestion
    notes: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "date": self.date,
            "logged_at": self.logged_at,
            "source": self.source,
            "entries": [e.to_dict() for e in self.entries],
        }
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkoutEvent:
        return cls(
            id=d["id"], date=d["date"],
            entries=[WorkoutEntry.from_dict(e) for e in d.get("entries", [])],
            source=d.get("source", {}), logged_at=d.get("logged_at", ""),
            notes=d.get("notes"), schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    @property
    def workout_type(self) -> str:
        """chest+back / cardio / mixed ... derived from entry categories."""
        cats: list[str] = []
        for e in self.entries:
            c = _CATEGORY_CACHE.get(e.exercise_id)
            if c and c not in cats:
                cats.append(c)
        return " + ".join(cats[:3]) if cats else "training"


# Filled lazily by registry to avoid a circular import.
_CATEGORY_CACHE: dict[str, str] = {}
