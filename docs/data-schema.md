# Data Schemas

Everything under `data/` is version-controlled JSON with a
`schema_version` field. The README and all SVGs are **views**; `data/`
is the only source of truth, and every derived number is recomputable
via `python -m irongraph.ingest --regen`.

```text
data/
├── registry/
│   ├── exercises.json          # canonical exercise registry (56 seeded)
│   ├── custom-exercises.json   # auto-created from quest issues
│   └── videos.json             # hand-verified technique videos (opt-in)
├── workouts/
│   └── 2026/
│       └── 2026-07-12--issue-42.json   # one WorkoutEvent, append-only
├── personal-records.json       # append-only PR history per exercise
├── achievements.json           # append-only unlock log
├── profile.json                # XP, level, streaks, XP audit log
├── ingested.json               # idempotency ledger (issue → ingestion)
└── graph.json                  # generated knowledge graph + layout
```

## WorkoutEvent (`data/workouts/YYYY/…json`)

```json
{
  "schema_version": 1,
  "id": "issue-42",
  "date": "2026-07-12",
  "logged_at": "2026-07-12T21:41:03-07:00",
  "source": {"type": "github-issue", "issue_number": 42, "issue_url": "…"},
  "entries": [
    {
      "exercise_id": "barbell-bench-press",
      "exercise_name": "Barbell Bench Press",
      "modality": "weight_reps",
      "sets": [
        {"weight": 185, "unit": "lb", "reps": 6},
        {"weight": 185, "unit": "lb", "reps": 5}
      ],
      "notes": "paused reps",
      "raw": ""
    },
    {
      "exercise_id": "treadmill",
      "exercise_name": "Treadmill",
      "modality": "distance_time",
      "sets": [{"duration_s": 1500, "distance": 2.3, "distance_unit": "mi", "incline_pct": 3.0}]
    }
  ],
  "notes": "Chest and back day."
}
```

Key properties:

- **Sparse sets.** A set only carries the fields its modality needs.
  A plank has `duration_s`; a pull-up has `reps` (and `added_weight:
  true` + `weight` when loaded); nothing forces a weight onto everything.
- **Units as entered.** `84 kg` is stored as kg; normalization to lb
  happens at comparison time (`LB_PER_KG = 2.2046226218`), so the audit
  trail matches what the user typed.
- **Modalities**: `weight_reps` · `reps` · `time` · `distance_time` ·
  `weight_time`.

## personal-records.json

Per exercise, per record type, an **append-only history** — the last
element is current, everything earlier is the PR timeline:

```json
{
  "schema_version": 1,
  "exercises": {
    "barbell-bench-press": {
      "max_weight": [
        {"value": 180, "display": "180 lb × 6", "date": "2026-07-01", "workout_id": "issue-30"},
        {"value": 185, "display": "185 lb × 6", "date": "2026-07-12", "workout_id": "issue-42"}
      ],
      "max_e1rm":  [ … ],
      "rep_weight:6": [ … ]
    }
  }
}
```

Record types: `max_weight`, `max_e1rm` (Epley `w×(1+r/30)`, 1–12 reps
only), `rep_weight:N`, `max_reps`, `max_added`, `max_volume`,
`max_duration`, `max_distance`, `best_pace` (≥ 1 mile only). Cardio
records never compare across different machines/modalities — they are
scoped to one exercise id.

## Exercise registry entry

```json
{
  "id": "barbell-bench-press",
  "name": "Barbell Bench Press",
  "aliases": ["bench press", "bench", "flat bench"],
  "category": "chest",
  "primary_muscles": ["chest"],
  "secondary_muscles": ["triceps", "front-delts"],
  "movement_pattern": "horizontal-push",
  "equipment": "barbell",
  "modality": "weight_reps",
  "compound": true,
  "relations": {
    "variation_of": [], "similar_to": ["dumbbell-bench-press"],
    "progresses_to": [], "regresses_to": ["push-up"],
    "complementary_to": ["barbell-row"], "alternative_to": ["dumbbell-bench-press"]
  }
}
```

IDs are stable slugs — never rename one; add aliases instead. Custom
exercises land in `custom-exercises.json` with `"custom": true` and can
be enriched by hand later (the parser only needs the name to match).

## profile.json / achievements.json / ingested.json

- `profile.json` keeps XP with a full `xp_log` audit (every grant
  traceable to a workout id), plus current streak numbers.
- `achievements.json` is an append-only unlock log with dates and the
  workout that triggered each unlock.
- `ingested.json` maps `issue-N` → ingestion metadata; it is checked
  before anything else, making the whole pipeline idempotent.

## Privacy boundary

Public: workout performance (exercises, sets, reps, weights, cardio
metrics, optional notes). Local-only (gitignored `local/`): video search
cache, any AI conversation state. Never collected: bodyweight (unless
`privacy.publish_bodyweight: true`), location, gym name, health data.
