"""Knowledge-graph builder.

Produces data/graph.json: nodes (exercises) with a precomputed
deterministic force-directed layout clustered by category, plus typed
edges. The frontend only renders — no layout work in the browser
(same split as Multimodal Search's prepare_atlas step).
"""

from __future__ import annotations

import json
import math
import random

from . import paths
from .analytics import ExerciseStats
from .models import SCHEMA_VERSION
from .registry import Registry

EDGE_TYPES = ["variation_of", "similar_to", "progresses_to", "regresses_to",
              "complementary_to", "alternative_to"]

CLUSTERS = ["chest", "back", "shoulders", "biceps", "triceps", "legs",
            "glutes", "core", "cardio", "calisthenics", "mobility", "other"]


def _cluster_center(i: int, n: int, radius: float = 340.0) -> tuple[float, float]:
    a = 2 * math.pi * i / n - math.pi / 2
    return radius * math.cos(a), radius * math.sin(a)


def build_graph(registry: Registry, stats: dict[str, ExerciseStats],
                pr_recent: set[str] | None = None,
                recommended: set[str] | None = None) -> dict:
    pr_recent = pr_recent or set()
    recommended = recommended or set()
    exercises = registry.all()
    ids = {e.id for e in exercises}
    rng = random.Random(1337)

    used_clusters = [c for c in CLUSTERS if any(e.category == c for e in exercises)]
    centers = {c: _cluster_center(i, len(used_clusters)) for i, c in enumerate(used_clusters)}

    # --- edges ------------------------------------------------------------
    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for ex in exercises:
        for etype in EDGE_TYPES:
            for target in ex.relations.get(etype, []):
                if target not in ids:
                    continue
                key = (min(ex.id, target), max(ex.id, target), etype)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"source": ex.id, "target": target, "type": etype})
    # derived: same movement pattern (kept sparse — chain, don't clique)
    by_pattern: dict[str, list[str]] = {}
    for ex in exercises:
        if ex.movement_pattern and ex.movement_pattern != "other":
            by_pattern.setdefault(ex.movement_pattern, []).append(ex.id)
    for pattern, members in by_pattern.items():
        members.sort()
        for a, b in zip(members, members[1:]):
            key = (min(a, b), max(a, b), "same_movement_pattern")
            if key not in seen and not any(
                    (min(a, b), max(a, b), t) in seen for t in EDGE_TYPES):
                seen.add(key)
                edges.append({"source": a, "target": b, "type": "same_movement_pattern"})

    # --- layout -------------------------------------------------------------
    pos: dict[str, list[float]] = {}
    for ex in exercises:
        cx, cy = centers.get(ex.category, (0.0, 0.0))
        pos[ex.id] = [cx + rng.uniform(-80, 80), cy + rng.uniform(-80, 80)]

    neighbors: dict[str, list[str]] = {e.id: [] for e in exercises}
    for e in edges:
        neighbors[e["source"]].append(e["target"])
        neighbors[e["target"]].append(e["source"])

    id_list = [e.id for e in exercises]
    for _ in range(220):
        # spring attraction along edges
        for e in edges:
            pa, pb = pos[e["source"]], pos[e["target"]]
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            dist = max(math.hypot(dx, dy), 1e-3)
            ideal = 90.0 if e["type"] != "same_movement_pattern" else 130.0
            f = 0.012 * (dist - ideal)
            fx, fy = f * dx / dist, f * dy / dist
            pa[0] += fx; pa[1] += fy
            pb[0] -= fx; pb[1] -= fy
        # pairwise repulsion (n is small enough for O(n^2))
        for i, ida in enumerate(id_list):
            for idb in id_list[i + 1:]:
                pa, pb = pos[ida], pos[idb]
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                d2 = dx * dx + dy * dy
                if d2 > 200 * 200 or d2 < 1e-6:
                    continue
                d = math.sqrt(d2)
                f = 900.0 / d2
                fx, fy = f * dx / d, f * dy / d
                pa[0] -= fx; pa[1] -= fy
                pb[0] += fx; pb[1] += fy
        # gravity toward own cluster center
        for ex in exercises:
            cx, cy = centers.get(ex.category, (0.0, 0.0))
            p = pos[ex.id]
            p[0] += (cx - p[0]) * 0.015
            p[1] += (cy - p[1]) * 0.015

    # --- nodes ------------------------------------------------------------
    nodes = []
    for ex in exercises:
        st = stats.get(ex.id)
        nodes.append({
            "id": ex.id, "name": ex.name, "category": ex.category,
            "muscles": ex.primary_muscles, "pattern": ex.movement_pattern,
            "equipment": ex.equipment, "modality": ex.modality,
            "compound": ex.compound, "custom": ex.custom,
            "x": round(pos[ex.id][0], 1), "y": round(pos[ex.id][1], 1),
            "performed": bool(st and st.times_performed),
            "times_performed": st.times_performed if st else 0,
            "last_performed": st.last_performed if st else None,
            "trend": st.trend if st else "insufficient data",
            "recent_pr": ex.id in pr_recent,
            "recommended": ex.id in recommended,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "clusters": [{"id": c, "cx": round(centers[c][0], 1), "cy": round(centers[c][1], 1)}
                     for c in used_clusters],
        "nodes": nodes,
        "edges": edges,
    }


def write_graph(graph: dict) -> None:
    p = paths.graph_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(graph, indent=1) + "\n")
