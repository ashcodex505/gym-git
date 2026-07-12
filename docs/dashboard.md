# Local Dashboard

```bash
make dev     # → http://localhost:4870
```

FastAPI (localhost-bound) serving a zero-build vanilla-JS frontend.
The dashboard is a *view* over `data/` — it refreshes automatically when
data files change (mtime-based cache) and never writes workout data.

## Views

- **Command Center** (`1`) — level/XP, streaks, newest PRs,
  data-grounded recommendations, AI status.
- **Exercise Graph** (`2`) — the Obsidian-like knowledge universe:
  - node size = frequency · filled/hollow = performed/unexplored
  - green breathing halo = recent PR · gold dashed ring = recommended
  - inner dark core = compound movement · color = muscle cluster
  - drag to pan, scroll/pinch to zoom, minimap click/drag teleport,
    cluster legend fly-tos, filter chips (performed / unexplored /
    recent PRs / recommended), `/` focuses search, Enter jumps to the
    best match, `f` fits, `←/→` hop between a pinned node's neighbors
  - clicking a node opens the detail panel: current records, e1RM,
    sparkline with PR dots, recent performances, related exercises
    (click to navigate, with back), technique video, Ask-AI shortcut
- **Timeline** (`3`) — every session, chronological, with full sets.
- **PR Vault** (`4`) — every current record + its full history chain.
- **Achievements** (`5`) — unlocked and still-locked, no spoilers hidden.
- **AI Coach** (`6`) — chat grounded in your actual history; 🌐 toggle
  enables Google-Search-grounded answers with source links.

**⌘K** opens the command palette from anywhere: jump to any view or fly
directly to any exercise node. Number keys `1–6` switch views. URLs
support deep links (`/#graph`, `/#vault`, …).

## API

Interactive docs at `http://localhost:4870/api/docs`. Endpoints:
`/api/summary`, `/api/graph`, `/api/exercises`, `/api/exercise/{id}`,
`/api/workouts`, `/api/records`, `/api/achievements`,
`/api/recommendations`, `POST /api/ai/ask`.
