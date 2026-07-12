# AI Integration

## Model choice (researched July 2026)

- SDK: **`google-genai`** — the unified SDK (the old
  `google-generativeai` package is deprecated).
- Default model: **`gemini-3.5-flash`** — current frontier-speed model
  with a free tier and Google Search grounding (5,000 free grounded
  prompts/month across the Gemini 3.x family as of writing). Note that
  Gemini 2.0-era models are being retired (2.0 Flash shut down
  June 2026), so IronGraph defaults to the 3.x line and lets you
  override with `IRONGRAPH_GEMINI_MODEL` if the lineup shifts.
- Continuity: the owner's Multimodal Search project already uses the
  Gemini ecosystem — one API key covers both.

## Hard rules

1. **AI is an enhancement, never a dependency.** The ingestion pipeline
   never imports `ai.py`. No key ⇒ the dashboard shows the coach as
   offline; everything else is fully functional. A failed Gemini call
   returns a structured error and can never lose workout data.
2. **No invented history.** Prompts inject the user's *actual* recorded
   stats under a `USER HISTORY` header, and the system prompt requires
   the model to (a) treat that as the only history that exists, and
   (b) prefix history-derived statements with "From your history:".
3. **No medical claims.** System prompt forbids diagnoses/treatment;
   every answer carries a one-line "not medical advice" note.

## Endpoints

- `POST /api/ai/ask` — `{question, exercise_id?, grounding?}`.
  With `grounding: true`, Google Search grounding is enabled and the
  response includes the grounding source URLs, rendered as links.
- `GET /api/recommendations` — **deterministic, LLM-free** engine
  (`ai.recommend`): unexplored variations of your most-performed lifts +
  movement-pattern gap detection (e.g. 14 horizontal-push sessions vs 3
  pulls). Each suggestion states the exact data it derives from. This
  runs with zero API keys.

## Technique videos — no hallucinated URLs, ever

Three tiers (see `irongraph/videos.py`):

1. **Curated registry** `data/registry/videos.json` — URLs a human has
   actually opened and watched. Ships empty *by design*: pre-filling it
   with model-remembered video IDs would be exactly the hallucination
   failure this architecture bans.
2. **YouTube Data API** (`YOUTUBE_API_KEY` set) — real results from the
   official search API, cached in gitignored `local/`.
3. **Fallback** — a `youtube.com/results?search_query=<exercise>
   technique form tutorial` deep link: always real, always relevant.

Every exercise detail panel therefore always has a working "▶ technique
video" action, and its reliability tier is explicit in the API payload.
