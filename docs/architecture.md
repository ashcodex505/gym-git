# IronGraph Architecture

> How a real-world workout becomes a verified, human-authored Git commit.

## The pipeline

```text
                 21:07 America/Phoenix (04:07 UTC — AZ has no DST)
                                   │
                                   ▼
                 .github/workflows/daily-quest.yml
                 creates the quest issue (gh issue create)
                 labels: daily-quest · workout · awaiting-log
                                   │
                     user edits issue on phone,
                     checks [x] boxes, adds numbers,
                     closes issue (or labels log-workout)
                                   │
                                   ▼
                 .github/workflows/process-workout.yml
                                   │
        ┌──────────────────────────┴───────────────────────────┐
        │              python -m irongraph.ingest              │
        │                                                      │
        │  parser.py ──► validated entries  (or exit 2 +       │
        │                helpful issue comment, issue reopened) │
        │  idempotency: issue number is the ingestion key      │
        │                (duplicate ⇒ exit 3, no-op)           │
        │                                                      │
        │  WorkoutEvent  ──►  data/workouts/YYYY/*.json        │
        │       │                                              │
        │       ├─► records.py       PR detection (append-only)│
        │       ├─► achievements.py  declarative unlock rules  │
        │       ├─► streaks.py       activity + weekly streaks │
        │       ├─► gamify.py        XP / levels               │
        │       ├─► graphbuild.py    data/graph.json + layout  │
        │       ├─► svggen.py        generated/*.svg           │
        │       ├─► readmegen.py     README.md                 │
        │       └─► commitmsg.py     subject + body            │
        └──────────────────────────┬───────────────────────────┘
                                   ▼
                 python -m irongraph.gitcommit
                 · git config user.name  "Ashish Kurse"
                 · git config user.email "ashishkurse@gmail.com"
                 · ONE atomic commit (data + records + charts + README)
                 · re-reads `git log -1` metadata
                 · HARD-FAILS + rolls back if author ≠ configured human
                                   │
                                   ▼
                 git push to default branch
                 → eligible for the GitHub contribution graph
```

## Domain separation

| Module | Responsibility | Depends on |
|---|---|---|
| `models.py` | canonical dataclasses, unit conversion | — |
| `registry.py` | exercise registry + aliases + custom exercises | models |
| `parser.py` | issue markdown → entries (untrusted input boundary) | registry |
| `records.py` | PR engine, append-only record history | models |
| `analytics.py` | e1RM (Epley), trends, per-exercise stats | models |
| `streaks.py` | activity + weekly-consistency streaks | — |
| `achievements.py` | declarative achievement definitions | records, streaks |
| `gamify.py` | XP grants, level curve | config |
| `graphbuild.py` | knowledge graph + deterministic force layout | registry |
| `svggen.py` | pure-Python SVG cards/charts | — |
| `readmegen.py` | README as a *view* over data/ | — |
| `commitmsg.py` | commit subject/body generation | records |
| `ingest.py` | orchestrator CLI | all of the above |
| `gitcommit.py` | author config + commit + metadata verification | config |
| `server/` | FastAPI read-mostly API + static frontend | all |
| `ai.py`, `videos.py` | optional intelligence (never load-bearing) | analytics |

Every engine is a pure function over `data/` — all derived numbers are
recomputable from workout history (`python -m irongraph.ingest --regen`).

## Design decisions

- **JSON files over SQLite** — human-readable, Git-diff-friendly,
  auditable in the GitHub UI, trivially migratable (every file carries
  `schema_version`). Scale is ~365 small files/year; nothing needs a DB.
- **One atomic commit per workout** — one workout = one contribution
  event = one coherent point in history. Data, records, charts, README
  all move together.
- **Layout computed in Python, not the browser** — same split as the
  Multimodal Search reference (its `prepare_atlas.py`): the frontend is a
  pure renderer, startup is instant, and layout is deterministic
  (seeded), so graph.json diffs stay small.
- **Zero-build frontend** — vanilla ES modules + canvas. No node
  toolchain to install or break; `make dev` is the entire loop.
- **AI strictly optional** — a failed Gemini call can never lose workout
  data; the ingestion path never imports `ai.py`.

## Frontend (web/)

Canvas renderer (`graph.js`) with a dirty-flag rAF loop, pan/zoom with
scale clamps, minimap teleport, cluster legend fly-tos, filter chips,
find-node search with Enter-jump, pinned node detail panel, ←/→ neighbor
hopping, ⌘K command palette — the interaction grammar inherited from the
Multimodal Search dashboard, retuned for an exercise graph:

- node **size** = training frequency
- **filled vs hollow** = performed vs unexplored
- **green breathing halo** = recent PR
- **gold dashed ring** = recommended
- **inner dark core** = compound movement
- **color** = muscle-group cluster
