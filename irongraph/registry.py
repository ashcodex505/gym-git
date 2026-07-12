"""Exercise registry: canonical + custom exercises, alias resolution.

Unknown exercises never break ingestion — they are auto-registered as
custom exercises (data/registry/custom-exercises.json) with a modality
inferred from how the user logged them.
"""

from __future__ import annotations

import json
import re

from . import models, paths
from .models import Exercise


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "exercise"


class Registry:
    def __init__(self, exercises: list[Exercise]):
        self.by_id: dict[str, Exercise] = {}
        self._alias_index: dict[str, str] = {}
        for ex in exercises:
            self.add(ex, persist=False)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> Registry:
        exercises: list[Exercise] = []
        core = json.loads(paths.registry_path().read_text())
        for d in core["exercises"]:
            exercises.append(Exercise.from_dict(d))
        custom_p = paths.custom_registry_path()
        if custom_p.exists():
            for d in json.loads(custom_p.read_text()).get("exercises", []):
                d["custom"] = True
                exercises.append(Exercise.from_dict(d))
        return cls(exercises)

    def add(self, ex: Exercise, persist: bool = True) -> None:
        self.by_id[ex.id] = ex
        models._CATEGORY_CACHE[ex.id] = ex.category
        self._alias_index[self._norm(ex.name)] = ex.id
        self._alias_index[self._norm(ex.id)] = ex.id
        for a in ex.aliases:
            self._alias_index[self._norm(a)] = ex.id
        if persist and ex.custom:
            self._persist_custom()

    @staticmethod
    def _norm(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9]+", " ", s).strip()
        # cheap singularization so "pushups" == "push ups" == "push-up"
        return re.sub(r"s\b", "", s)

    def resolve(self, name: str) -> Exercise | None:
        return self.by_id.get(self._alias_index.get(self._norm(name), ""))

    # ------------------------------------------------------------------
    def register_custom(
        self,
        name: str,
        modality: models.Modality = "weight_reps",
        category: str = "other",
        primary_muscles: list[str] | None = None,
        equipment: str = "other",
        movement_pattern: str = "other",
    ) -> Exercise:
        """Create (and persist) a custom exercise for an unknown name."""
        base = _slug(name)
        eid = base
        n = 2
        while eid in self.by_id:
            eid = f"{base}-{n}"
            n += 1
        ex = Exercise(
            id=eid, name=name.strip(), category=category,
            primary_muscles=primary_muscles or [], equipment=equipment,
            movement_pattern=movement_pattern, modality=modality, custom=True,
        )
        self.add(ex, persist=True)
        return ex

    def _persist_custom(self) -> None:
        p = paths.custom_registry_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        customs = [e.to_dict() for e in self.by_id.values() if e.custom]
        p.write_text(json.dumps(
            {"schema_version": models.SCHEMA_VERSION, "exercises": customs},
            indent=2) + "\n")

    # ------------------------------------------------------------------
    def all(self) -> list[Exercise]:
        return list(self.by_id.values())

    def by_category(self) -> dict[str, list[Exercise]]:
        out: dict[str, list[Exercise]] = {}
        for ex in self.by_id.values():
            out.setdefault(ex.category, []).append(ex)
        return out
