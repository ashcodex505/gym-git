"""Optional Gemini-powered exercise intelligence.

Model choice (researched July 2026): `gemini-3.5-flash` via the unified
`google-genai` SDK — current free-tier model with Google Search grounding
(5,000 grounded prompts/month free). Override with IRONGRAPH_GEMINI_MODEL.

Hard rules:
* Core tracking NEVER depends on this module — every function degrades to
  a clear "AI unavailable" result when no key / SDK / network.
* The prompt separates *your actual history* (injected verbatim from
  data/) from general knowledge, and the system prompt forbids inventing
  history.
* Responses carry a short non-obnoxious disclaimer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .analytics import ExerciseStats
from .registry import Registry

DEFAULT_MODEL = "gemini-3.5-flash"

SYSTEM = """You are IronGraph's exercise coach — precise, encouraging, never bro-science.
Rules:
- The user's REAL workout history is given under 'USER HISTORY'. Never invent, extrapolate, or assume history that is not listed there.
- When you reference their history, prefix with 'From your history:'. General exercise knowledge needs no prefix. Clearly separate the two.
- Recommendations must be conservative progressions; never prescribe dramatic load jumps.
- No medical diagnoses or injury treatment. If asked, advise seeing a professional.
- Be concise: short paragraphs, small lists. No hype."""

DISCLAIMER = "_AI-generated training guidance — not medical advice._"


@dataclass
class AIResult:
    available: bool
    text: str = ""
    grounding_urls: list[str] = field(default_factory=list)
    error: str = ""


def _client():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None, "No GEMINI_API_KEY set — add one to .env to enable the AI coach (free tier works)."
    try:
        from google import genai
    except ImportError:
        return None, "google-genai not installed — run: pip install 'irongraph[ai]'"
    return genai.Client(api_key=key), ""


def history_context(stats: dict[str, ExerciseStats], registry: Registry, limit: int = 40) -> str:
    """Compact, factual history block injected into prompts."""
    lines = []
    ranked = sorted(stats.values(), key=lambda s: -s.times_performed)[:limit]
    for st in ranked:
        ex = registry.by_id.get(st.exercise_id)
        if not ex:
            continue
        bits = [f"{ex.name}: {st.times_performed}x, last {st.last_performed}"]
        if st.best_weight_lb:
            bits.append(f"best {st.best_weight_lb:g} lb × {st.best_weight_reps or '?'}")
        if st.best_e1rm:
            bits.append(f"e1RM ~{st.best_e1rm:g} lb")
        if st.best_reps and not st.best_weight_lb:
            bits.append(f"best {st.best_reps} reps")
        if st.best_distance_mi:
            bits.append(f"best {st.best_distance_mi:.1f} mi")
        bits.append(f"trend: {st.trend}")
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines) if lines else "(no workouts recorded yet)"


def ask(question: str, stats: dict[str, ExerciseStats], registry: Registry,
        exercise_id: str | None = None, use_grounding: bool = False) -> AIResult:
    client, err = _client()
    if client is None:
        return AIResult(available=False, error=err)
    model = os.environ.get("IRONGRAPH_GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    focus = ""
    if exercise_id and (ex := registry.by_id.get(exercise_id)):
        focus = (f"\nCURRENT EXERCISE: {ex.name} — primary: {', '.join(ex.primary_muscles)}; "
                 f"pattern: {ex.movement_pattern}; equipment: {ex.equipment}.")
    prompt = (f"USER HISTORY (real recorded data, the ONLY history that exists):\n"
              f"{history_context(stats, registry)}\n{focus}\n\nQUESTION: {question.strip()[:2000]}")
    try:
        from google.genai import types
        cfg_kwargs: dict = {"system_instruction": SYSTEM}
        if use_grounding:
            cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        urls: list[str] = []
        try:
            gm = resp.candidates[0].grounding_metadata
            for chunk in (gm.grounding_chunks or []):
                if chunk.web and chunk.web.uri:
                    urls.append(chunk.web.uri)
        except Exception:
            pass
        return AIResult(available=True, text=(resp.text or "") + "\n\n" + DISCLAIMER,
                        grounding_urls=urls[:5])
    except Exception as e:  # AI failure must never break anything upstream
        return AIResult(available=False, error=f"Gemini call failed: {e.__class__.__name__}: {e}")


# ---------------------------------------------------------------- gap analysis
PUSH_PULL_PATTERNS = {
    "horizontal-push": "horizontal-pull",
    "horizontal-pull": "horizontal-push",
    "vertical-push": "vertical-pull",
    "vertical-pull": "vertical-push",
    "squat": "hip-hinge",
    "hip-hinge": "squat",
}


def recommend(stats: dict[str, ExerciseStats], registry: Registry, limit: int = 6) -> list[dict]:
    """Deterministic, history-grounded recommendations (no LLM needed):
    1. unexplored variations of your most-performed exercises,
    2. movement-pattern gaps (e.g. lots of horizontal push, little pull),
    3. logical progressions you're close to.
    Each item says exactly WHY, from your data."""
    recs: list[dict] = []
    performed = {i for i, s in stats.items() if s.times_performed > 0}
    top = sorted((s for s in stats.values() if s.times_performed > 0),
                 key=lambda s: -s.times_performed)[:8]

    for st in top:
        ex = registry.by_id.get(st.exercise_id)
        if not ex:
            continue
        for rel_type, label in (("variation_of", "variation of"), ("similar_to", "similar to"),
                                ("alternative_to", "alternative to")):
            ids = ex.relations.get(rel_type, []) + [
                other.id for other in registry.all()
                if ex.id in other.relations.get(rel_type, [])]
            for rid in ids:
                if rid in performed or rid not in registry.by_id:
                    continue
                recs.append({"exercise_id": rid, "name": registry.by_id[rid].name,
                             "reason": f"You've done {ex.name} {st.times_performed}× but never this {label} it.",
                             "kind": "variation"})

    pattern_counts: dict[str, int] = {}
    for i in performed:
        ex = registry.by_id.get(i)
        sti = stats.get(i)
        if ex and sti:
            pattern_counts[ex.movement_pattern] = pattern_counts.get(ex.movement_pattern, 0) + sti.times_performed
    for pat, count in sorted(pattern_counts.items(), key=lambda kv: -kv[1]):
        opp = PUSH_PULL_PATTERNS.get(pat)
        if not opp:
            continue
        opp_count = pattern_counts.get(opp, 0)
        if count >= 5 and opp_count * 2 < count:
            for ex in registry.all():
                if ex.movement_pattern == opp and ex.id not in performed:
                    recs.append({"exercise_id": ex.id, "name": ex.name,
                                 "reason": f"Movement gap: {count} {pat} sessions vs {opp_count} {opp}.",
                                 "kind": "gap"})
                    break
    seen: set[str] = set()
    out = []
    for r in recs:
        if r["exercise_id"] not in seen:
            seen.add(r["exercise_id"])
            out.append(r)
    return out[:limit]
