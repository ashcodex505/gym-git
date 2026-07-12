# GitHub Workflows

## daily-quest.yml — the nightly quest

- **Schedule**: `cron: "7 4 * * *"` = 04:07 UTC = **21:07
  America/Phoenix** every day of the year (Arizona doesn't observe DST,
  so one UTC line is exact). The `:07` minute is deliberate: GitHub's
  cron queue is congested on the hour and off-hour schedules fire more
  reliably. `workflow_dispatch` allows manual runs.
- **Permissions**: `issues: write`, `contents: read` — least privilege.
- **Dedupe**: searches for an open `daily-quest` issue containing
  today's `irongraph:quest date=YYYY-MM-DD` marker before creating one,
  so retries/manual runs can't double-post.
- Ensures all labels exist (`--force` is create-or-update), builds the
  body with `python -m irongraph.quest` (which injects your level, XP,
  and current PR hints next to each exercise), assigns the repo owner.

## process-workout.yml — quest completion

- **Triggers**: issue `closed`, or `labeled` with `log-workout` — only
  for issues carrying the `daily-quest` label. Closing is the normal
  path; the label lets you log without closing or force a retry.
- **Permissions**: `contents: write`, `issues: write`.
- **Concurrency**: a `process-workout` group serializes runs so two
  rapid closes can't race the push.
- **Untrusted input handling**: the issue body goes through an env var
  into a file (`printf '%s' "$ISSUE_BODY"`), then into Python argv. It
  is never interpolated into shell syntax, filenames, or git commands.
  The parser additionally length-clamps and strips backticks from any
  text that can reach commit messages or SVG/markdown output.
- **Outcomes** (from the ingest summary JSON):
  - `ok` → one atomic commit via `irongraph.gitcommit` (author
    configured **and verified** — see
    [contribution-attribution.md](contribution-attribution.md)), push to
    the default branch, celebratory comment with PRs/achievements/XP.
  - `invalid` → no commit at all; comment lists each problem line;
    issue is reopened + labeled `needs-fix`. The user's text is
    untouched — fix and close again.
  - `duplicate` → no-op comment (idempotency ledger hit).

## Failure modes considered

| Case | Behavior |
|---|---|
| Same issue processed twice | `ingested.json` key ⇒ duplicate no-op |
| Issue closed accidentally (empty) | validation fails politely, reopened with instructions |
| Malformed lines | listed one-by-one in a comment, nothing recorded |
| Workflow retry after crash | ingestion is deterministic; if the commit already landed, the next run is a duplicate no-op |
| Author misconfiguration | commit rolled back, workflow fails, nothing pushed |
| Gemini/network down | irrelevant — AI is not in the ingestion path |
| Concurrent quests | concurrency groups serialize both workflows |
