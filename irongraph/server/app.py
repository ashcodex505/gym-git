"""FastAPI backend for the local dashboard.

Read-mostly API over data/ — the dashboard is a *view* of the Git-tracked
truth, plus optional AI endpoints. Bound to localhost only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import ai as ai_mod
from .. import paths, records, videos
from ..achievements import ACHIEVEMENTS, load_unlocked
from ..analytics import compute_exercise_stats, load_all_events
from ..config import load_config
from ..gamify import load_profile, xp_for_level
from ..registry import Registry
from ..streaks import compute_streaks

app = FastAPI(title="IronGraph", docs_url="/api/docs")


@app.middleware("http")
async def no_cache(request, call_next):
    """Localhost dev tool: never let the browser serve stale app.js/CSS —
    a cached old script silently breaks new UI (buttons with no handler)."""
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


# ---- lazily cached state (invalidated by data mtime) -----------------------
class _State:
    def __init__(self) -> None:
        self.mtime = -1.0

    def _data_mtime(self) -> float:
        latest = 0.0
        d = paths.data_dir()
        if d.exists():
            for f in d.rglob("*.json"):
                latest = max(latest, f.stat().st_mtime)
        return latest

    def refresh(self) -> None:
        m = self._data_mtime()
        if m == self.mtime:
            return
        self.mtime = m
        self.registry = Registry.load()
        self.events = load_all_events()
        self.stats = compute_exercise_stats(self.events)
        self.records = records.load_records()
        self.profile = load_profile()
        self.unlocked = load_unlocked()


S = _State()


@app.get("/api/summary")
def summary():
    S.refresh()
    cfg = load_config()
    st = compute_streaks([e.date for e in S.events], cfg.weekly_consistency_target)
    prof = S.profile
    latest = S.events[-1] if S.events else None
    prs_recent = []
    for ex_id, kinds in S.records.get("exercises", {}).items():
        for rtype, hist in kinds.items():
            if hist:
                prs_recent.append({"exercise_id": ex_id, "type": rtype, **hist[-1]})
    prs_recent.sort(key=lambda p: p["date"], reverse=True)
    return {
        "level": prof.get("level", 1), "title": prof.get("title", "Novice"),
        "xp": prof.get("xp", 0),
        "xp_next": xp_for_level(prof.get("level", 1) + 1),
        "xp_cur_floor": xp_for_level(prof.get("level", 1)),
        "total_workouts": len(S.events),
        "total_prs": sum(len(h) for ex in S.records.get("exercises", {}).values() for h in ex.values()),
        "exercises_tried": len(S.stats),
        "streaks": st.__dict__,
        "latest_workout": {
            "date": latest.date, "type": latest.workout_type,
            "entries": len(latest.entries)} if latest else None,
        "newest_prs": prs_recent[:5],
        "workouts_this_month": sum(1 for e in S.events if latest and e.date[:7] == latest.date[:7]),
        "recommendations": ai_mod.recommend(S.stats, S.registry, limit=4),
        "ai_available": bool(os.environ.get("GEMINI_API_KEY")),
    }


@app.get("/api/graph")
def graph():
    p = paths.graph_path()
    if not p.exists():
        from ..graphbuild import build_graph
        return build_graph(Registry.load(), {})
    return json.loads(p.read_text())


@app.get("/api/exercises")
def exercises():
    S.refresh()
    out = []
    for ex in S.registry.all():
        st = S.stats.get(ex.id)
        out.append({**ex.to_dict(),
                    "times_performed": st.times_performed if st else 0,
                    "last_performed": st.last_performed if st else None,
                    "trend": st.trend if st else "insufficient data"})
    return out


@app.get("/api/exercise/{ex_id}")
def exercise_detail(ex_id: str):
    S.refresh()
    ex = S.registry.by_id.get(ex_id)
    if not ex:
        raise HTTPException(404, "unknown exercise")
    st = S.stats.get(ex_id)
    kinds = S.records.get("exercises", {}).get(ex_id, {})
    current_records = {k: v[-1] for k, v in kinds.items() if v}
    perfs = []
    for ev in reversed(S.events):
        for en in ev.entries:
            if en.exercise_id == ex_id:
                perfs.append({"date": ev.date, "sets": [s.to_dict() for s in en.sets],
                              "notes": en.notes})
        if len(perfs) >= 10:
            break
    related = {}
    for rtype, ids in ex.relations.items():
        rel = [{"id": i, "name": S.registry.by_id[i].name,
                "performed": bool(S.stats.get(i) and S.stats[i].times_performed)}
               for i in ids if i in S.registry.by_id]
        if rel:
            related[rtype] = rel
    return {
        "exercise": ex.to_dict(),
        "stats": st.__dict__ if st else None,
        "records": current_records,
        "record_history": kinds,
        "recent_performances": perfs,
        "related": related,
        "video": videos.resolve_video(ex_id, S.registry, os.environ.get("YOUTUBE_API_KEY", "")),
    }


@app.get("/api/workouts")
def workouts():
    S.refresh()
    return [{"id": e.id, "date": e.date, "type": e.workout_type,
             "entries": [en.to_dict() for en in e.entries], "notes": e.notes,
             "source": e.source}
            for e in reversed(S.events)]


@app.get("/api/records")
def all_records():
    S.refresh()
    out = []
    for ex_id, kinds in S.records.get("exercises", {}).items():
        ex = S.registry.by_id.get(ex_id)
        for rtype, hist in kinds.items():
            if hist:
                out.append({"exercise_id": ex_id,
                            "exercise_name": ex.name if ex else ex_id,
                            "type": rtype, "current": hist[-1], "history": hist})
    out.sort(key=lambda r: r["current"]["date"], reverse=True)
    return out


@app.get("/api/achievements")
def achievements():
    S.refresh()
    unlocked_ids = {u["id"] for u in S.unlocked["unlocked"]}
    return {
        "unlocked": S.unlocked["unlocked"],
        "locked": [{"id": a.id, "name": a.name, "emoji": a.emoji,
                    "description": a.description}
                   for a in ACHIEVEMENTS if a.id not in unlocked_ids],
    }


class NewExercise(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = "other"
    modality: str = "weight_reps"
    equipment: str = "other"
    movement_pattern: str = "other"
    primary_muscles: list[str] = Field(default_factory=list)
    secondary_muscles: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)  # names or ids → similar_to
    compound: bool = False


VALID_CATEGORIES = {"chest", "back", "shoulders", "biceps", "triceps", "legs",
                    "glutes", "core", "cardio", "calisthenics", "mobility", "other"}
VALID_MODALITIES = {"weight_reps", "reps", "time", "distance_time", "weight_time"}


@app.post("/api/exercises", status_code=201)
def add_exercise(body: NewExercise):
    """Add a custom exercise from the dashboard. Persists to
    data/registry/custom-exercises.json and rebuilds data/graph.json —
    both Git-tracked, so the change survives a push like any workout."""
    S.refresh()
    reg = S.registry
    name = body.name.strip()
    existing = reg.resolve(name)
    if existing:
        raise HTTPException(409, f"'{name}' already exists as '{existing.name}'")
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
    if body.modality not in VALID_MODALITIES:
        raise HTTPException(422, f"modality must be one of: {', '.join(sorted(VALID_MODALITIES))}")

    related_ids, unresolved = [], []
    for r in body.related:
        hit = reg.resolve(r.strip()) if r.strip() else None
        (related_ids.append(hit.id) if hit else unresolved.append(r.strip()))

    _clean = lambda xs: [x.strip().lower().replace(" ", "-") for x in xs if x.strip()][:8]  # noqa: E731
    ex = reg.register_custom(
        name,
        modality=body.modality,  # type: ignore[arg-type]
        category=body.category,
        primary_muscles=_clean(body.primary_muscles),
        secondary_muscles=_clean(body.secondary_muscles),
        equipment=body.equipment.strip().lower() or "other",
        movement_pattern=body.movement_pattern.strip().lower().replace(" ", "-") or "other",
        aliases=[a.strip() for a in body.aliases if a.strip()][:6],
        relations={"similar_to": related_ids} if related_ids else None,
        compound=body.compound,
    )
    # rebuild the graph so the new node appears (and is committable)
    from ..graphbuild import build_graph, write_graph
    write_graph(build_graph(reg, S.stats))
    S.mtime = -1.0  # force refresh on next read
    return {"exercise": ex.to_dict(), "unresolved_related": unresolved,
            "files_changed": ["data/registry/custom-exercises.json", "data/graph.json"]}


class EditExercise(BaseModel):
    """All fields optional — only supplied ones change. The id never changes."""
    name: str | None = Field(default=None, min_length=2, max_length=80)
    category: str | None = None
    modality: str | None = None
    equipment: str | None = None
    movement_pattern: str | None = None
    primary_muscles: list[str] | None = None
    secondary_muscles: list[str] | None = None
    aliases: list[str] | None = None
    related: list[str] | None = None   # names/ids → replaces similar_to
    compound: bool | None = None


@app.put("/api/exercises/{ex_id}")
def edit_exercise(ex_id: str, body: EditExercise):
    S.refresh()
    reg = S.registry
    ex = reg.by_id.get(ex_id)
    if not ex:
        raise HTTPException(404, "unknown exercise")
    if body.category is not None and body.category not in VALID_CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
    if body.modality is not None and body.modality not in VALID_MODALITIES:
        raise HTTPException(422, f"modality must be one of: {', '.join(sorted(VALID_MODALITIES))}")
    if body.name is not None:
        clash = reg.resolve(body.name.strip())
        if clash and clash.id != ex_id:
            raise HTTPException(409, f"'{body.name.strip()}' already belongs to '{clash.name}'")

    unresolved: list[str] = []
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name.strip()
    if body.category is not None:
        fields["category"] = body.category
    if body.modality is not None:
        fields["modality"] = body.modality
    if body.equipment is not None:
        fields["equipment"] = body.equipment.strip().lower() or "other"
    if body.movement_pattern is not None:
        fields["movement_pattern"] = body.movement_pattern.strip().lower().replace(" ", "-") or "other"
    _clean = lambda xs: [x.strip().lower().replace(" ", "-") for x in xs if x.strip()][:8]  # noqa: E731
    if body.primary_muscles is not None:
        fields["primary_muscles"] = _clean(body.primary_muscles)
    if body.secondary_muscles is not None:
        fields["secondary_muscles"] = _clean(body.secondary_muscles)
    if body.aliases is not None:
        fields["aliases"] = [a.strip() for a in body.aliases if a.strip()][:6]
    if body.compound is not None:
        fields["compound"] = body.compound
    if body.related is not None:
        ids = []
        for r in body.related:
            hit = reg.resolve(r.strip()) if r.strip() else None
            (ids.append(hit.id) if hit and hit.id != ex_id else unresolved.append(r.strip()) if r.strip() else None)
        fields["relations"] = {**ex.relations, "similar_to": ids}

    ex = reg.update_exercise(ex_id, fields)
    from ..graphbuild import build_graph, write_graph
    write_graph(build_graph(reg, S.stats))
    S.mtime = -1.0
    return {"exercise": ex.to_dict(), "unresolved_related": unresolved,
            "files_changed": ["data/registry/custom-exercises.json", "data/graph.json"]}


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    exercise_id: str | None = None
    grounding: bool = False


@app.post("/api/ai/ask")
def ai_ask(body: AskBody):
    S.refresh()
    r = ai_mod.ask(body.question, S.stats, S.registry,
                   exercise_id=body.exercise_id, use_grounding=body.grounding)
    return r.__dict__


@app.get("/api/recommendations")
def recommendations():
    S.refresh()
    return ai_mod.recommend(S.stats, S.registry, limit=8)


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


paths.generated_dir().mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=paths.generated_dir()), name="generated")
app.mount("/", StaticFiles(directory=WEB_DIR), name="static")
