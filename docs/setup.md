# Setup Guide

## Local dashboard (2 minutes)

```bash
git clone <your-irongraph-repo>
cd <repo>
cp .env.example .env      # optional: add GEMINI_API_KEY / YOUTUBE_API_KEY
make setup                # venv + deps + registry sanity check
make dev                  # → http://localhost:4870
```

Requires Python 3.11+ (`make setup` tries 3.13 → 3.12 → 3.11).

Useful targets: `make test` · `make lint` · `make type` · `make regen`
(rebuild README/SVGs/graph from data) · `make quest` (preview tonight's
quest issue).

## GitHub automation

Works out of the box on a standalone public repo — both workflows use
the built-in `GITHUB_TOKEN`, no PAT and no secrets needed:

1. Push this repository to GitHub (default branch: `main`).
2. Ensure Actions are enabled (Settings → Actions → Allow).
3. Settings → Actions → General → Workflow permissions →
   **Read and write permissions** (required for the workout commit push).
4. Optionally trigger the first quest manually: Actions → Daily Quest →
   Run workflow.

Nightly at ~21:07 America/Phoenix a quest issue appears. Fill it in,
close it, and watch the commit land — authored as you.

### Adapting to your own identity

Edit `config/irongraph.yml`:

```yaml
git_author:
  name: "Your Name"
  email: "email-linked-to-your-github-account@example.com"
timezone: "Your/Timezone"
```

If your timezone observes DST, adjust the two `cron:` lines in
`.github/workflows/daily-quest.yml` (GitHub cron is UTC-only; Arizona's
constant UTC-7 is why the shipped schedule is a single line).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Quest issue never appears | Actions disabled, or repo inactive >60 days (GitHub pauses schedules — push any commit or run manually) |
| "Quest not recorded yet" comment | Read the bullet list in the comment; fix the lines; close the issue again. Your text is never lost. |
| Workflow fails at "Commit workout" | Check Workflow permissions (step 3). The author-verification failure mode prints exactly what identity was found. |
| Duplicate close | Safe by design — ingestion keys on the issue number and exits as a no-op. |
| Dashboard empty | It reads `data/` — pull the repo after workflows have committed workouts. |
| AI coach "offline" | Add `GEMINI_API_KEY` to `.env` (free tier: https://aistudio.google.com/apikey). Core tracking never needs it. |
