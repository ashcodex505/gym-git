"""Exercise registry: canonical + custom exercises, alias resolution.

Unknown exercises never break ingestion — they are auto-registered as
custom exercises (data/registry/custom-exercises.json) with a modality
inferred from how the user logged them.
"""

from __future__ import annotations

import difflib
import json
import re

from . import models, paths
from .models import Exercise


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "exercise"


class Registry:
    # dashboard-editable fields (id is deliberately NOT editable — workout
    # history and PR records reference it forever)
    EDITABLE = ("name", "category", "primary_muscles", "secondary_muscles",
                "movement_pattern", "equipment", "modality", "compound",
                "aliases", "relations", "instructions")

    def __init__(self, exercises: list[Exercise]):
        self.by_id: dict[str, Exercise] = {}
        self._alias_index: dict[str, str] = {}
        self._overrides: dict[str, dict] = {}
        for ex in exercises:
            self.add(ex, persist=False)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> Registry:
        exercises: list[Exercise] = []
        core = json.loads(paths.registry_path().read_text())
        overrides: dict[str, dict] = {}
        custom_p = paths.custom_registry_path()
        custom_data: dict = {}
        if custom_p.exists():
            custom_data = json.loads(custom_p.read_text())
            overrides = custom_data.get("overrides", {})
        for d in core["exercises"]:
            # dashboard edits to built-in exercises live as overrides so the
            # core registry file stays pristine (small, reviewable diffs)
            if d["id"] in overrides:
                d = {**d, **overrides[d["id"]]}
            exercises.append(Exercise.from_dict(d))
        for d in custom_data.get("exercises", []):
            d["custom"] = True
            exercises.append(Exercise.from_dict(d))
        reg = cls(exercises)
        reg._overrides = overrides
        return reg

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

    def resolve_fuzzy(self, name: str, typo_cutoff: float = 0.82) -> Exercise | None:
        """Closest known exercise for a name with no exact/alias match —
        lets freeform logging land on the right exercise despite typos or
        casual wording, without ever guessing across genuinely different
        exercises.

        Two independent signals, deliberately *not* blended into one plain
        character-similarity score: a raw edit-distance ratio treats "press"
        as most of the string in both "Landmine Press" and "Standing Press",
        so it happily confuses unrelated lifts that merely share a common
        word (a real 2026-07 near-miss). Instead:

        * multi-word names match only via *token containment* (every word
          of the shorter name appears in the longer one) — "bench press"
          can find "Barbell Bench Press" but never "Landmine Press";
        * single-word names (or a single word against another single word)
          fall back to character-ratio, which is exactly what typo
          tolerance needs ("Deadlft" -> "Deadlift").

        Either way, if the best match ties with a *different* exercise,
        the name is left unmatched (ambiguous) so a new custom exercise is
        created instead of silently misattributing history to the wrong
        one — e.g. bare "Press" or "Squat" never auto-picks a variant."""
        key = self._norm(name)
        if not key or key in self._alias_index:
            return None
        q_tokens = set(key.split())
        scored: list[tuple[float, str]] = []
        for cand in self._alias_index:
            c_tokens = set(cand.split())
            if q_tokens and c_tokens and (q_tokens <= c_tokens or c_tokens <= q_tokens):
                coverage = min(len(q_tokens), len(c_tokens)) / max(len(q_tokens), len(c_tokens))
                scored.append((0.9 + 0.1 * coverage, cand))
            elif len(q_tokens) == 1 and len(c_tokens) == 1:
                ratio = difflib.SequenceMatcher(None, key, cand).ratio()
                if ratio >= typo_cutoff:
                    scored.append((ratio, cand))
        if not scored:
            return None
        scored.sort(key=lambda t: -t[0])
        best_score, best_key = scored[0]
        for score, cand in scored[1:]:
            if score >= best_score - 0.03 and self._alias_index[cand] != self._alias_index[best_key]:
                return None  # ambiguous between two distinct exercises
        return self.by_id.get(self._alias_index[best_key])

    # ------------------------------------------------------------------
    def register_custom(
        self,
        name: str,
        modality: models.Modality = "weight_reps",
        category: str = "other",
        primary_muscles: list[str] | None = None,
        equipment: str = "other",
        movement_pattern: str = "other",
        secondary_muscles: list[str] | None = None,
        aliases: list[str] | None = None,
        relations: dict[str, list[str]] | None = None,
        instructions: str = "",
        compound: bool = False,
    ) -> Exercise:
        """Create (and persist) a custom exercise for an unknown name.
        Relation targets must be existing exercise ids (unknown ones are
        dropped so a bad reference can never corrupt the graph)."""
        base = _slug(name)
        eid = base
        n = 2
        while eid in self.by_id:
            eid = f"{base}-{n}"
            n += 1
        clean_rel: dict[str, list[str]] = {}
        for rtype, targets in (relations or {}).items():
            valid = [t for t in targets if t in self.by_id]
            if valid:
                clean_rel[rtype] = valid
        ex = Exercise(
            id=eid, name=name.strip(), category=category,
            primary_muscles=primary_muscles or [], equipment=equipment,
            movement_pattern=movement_pattern, modality=modality, custom=True,
            secondary_muscles=secondary_muscles or [], aliases=aliases or [],
            relations=clean_rel, instructions=instructions[:2000], compound=compound,
        )
        self.add(ex, persist=True)
        return ex

    def update_exercise(self, eid: str, fields: dict) -> Exercise:
        """Apply edits (EDITABLE fields only) and persist them.

        Custom exercises are rewritten in place; edits to built-in
        exercises are stored as overrides in custom-exercises.json so the
        core registry file never churns. Relation targets that don't
        exist are dropped."""
        ex = self.by_id[eid]
        changes = {k: v for k, v in fields.items() if k in self.EDITABLE and v is not None}
        if "relations" in changes:
            changes["relations"] = {
                rt: [t for t in targets if t in self.by_id and t != eid]
                for rt, targets in changes["relations"].items() if targets}
        for k, v in changes.items():
            setattr(ex, k, v)
        if not ex.custom:
            self._overrides[eid] = {**self._overrides.get(eid, {}), **changes}
        self._reindex()
        self._persist_custom()
        return ex

    def _reindex(self) -> None:
        self._alias_index.clear()
        for ex in self.by_id.values():
            self._alias_index[self._norm(ex.name)] = ex.id
            self._alias_index[self._norm(ex.id)] = ex.id
            for a in ex.aliases:
                self._alias_index[self._norm(a)] = ex.id

    def _persist_custom(self) -> None:
        p = paths.custom_registry_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        customs = [e.to_dict() for e in self.by_id.values() if e.custom]
        data: dict = {"schema_version": models.SCHEMA_VERSION, "exercises": customs}
        if self._overrides:
            data["overrides"] = self._overrides
        p.write_text(json.dumps(data, indent=2) + "\n")

    # ------------------------------------------------------------------
    def all(self) -> list[Exercise]:
        return list(self.by_id.values())

    def by_category(self) -> dict[str, list[Exercise]]:
        out: dict[str, list[Exercise]] = {}
        for ex in self.by_id.values():
            out.setdefault(ex.category, []).append(ex)
        return out
