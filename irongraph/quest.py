"""Daily quest issue generation.

Prints the issue title and body; the GitHub workflow pipes these into
`gh issue create`. Timezone math: America/Phoenix never observes DST.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import load_config
from .gamify import load_profile, xp_for_level
from .records import load_records
from .registry import Registry

CATEGORY_META = [
    ("chest", "🏋️ Chest"),
    ("back", "🦾 Back"),
    ("shoulders", "🛡️ Shoulders"),
    ("biceps", "💪 Biceps"),
    ("triceps", "🔱 Triceps"),
    ("legs", "🦵 Legs"),
    ("glutes", "🍑 Glutes"),
    ("core", "🧿 Core / Abs"),
    ("cardio", "🏃 Cardio"),
    ("calisthenics", "🤸 Calisthenics"),
    ("mobility", "🧘 Mobility"),
    ("other", "📦 Other"),
]

EXAMPLES = """\
**How to log** — check `[x]` what you did and put your numbers after the `::`

| You did | Write |
|---|---|
| 185 lb for 6 reps | `185 lb x 6` |
| 3 sets of 5 at 185 | `3x5 @ 185 lb` or `185x5, 185x5, 185x5` |
| bodyweight 8 reps, then +25 lb for 5 | `bw x 8; +25 lb x 5` |
| treadmill 25 min, 2.3 miles, incline 3 | `25 min, 2.3 mi, incline 3` |
| incline walk 25 min at speed 3, incline 12 | `25 min, speed 3, incline 12` |
| stairmaster 30 min level 8 | `30 min level 8` |
| plank 2 min 15 s | `2m15s` |
| kg instead of lb | `84 kg x 5` |

Add a note with `//` at the end of a line. When you're done, **close this
issue** (or add the `log-workout` label) and IronGraph will commit your
workout, authored as you.
"""

CUSTOM_SECTION = """\
### ➕ Custom exercise
Not in the list? Add a line like:

```
- [x] Landmine Press [muscle: shoulders; equipment: barbell; modality: weight_reps] :: 70 lb x 10
```

- [ ] <exercise name> [muscle: ; equipment: ] ::
"""

NOTES_SECTION = """\
### 📝 Session notes
```text
(optional — anything about today's session)
```
"""


def _current_pr_hint(records: dict, ex_id: str) -> str:
    hist = records.get("exercises", {}).get(ex_id, {}).get("max_weight")
    if hist:
        return f"  <sub>PR {hist[-1]['display']}</sub>"
    hist = records.get("exercises", {}).get(ex_id, {}).get("max_reps")
    if hist:
        return f"  <sub>PR {hist[-1]['display']}</sub>"
    return ""


def build_quest(today: date | None = None) -> tuple[str, str]:
    cfg = load_config()
    tz = ZoneInfo(cfg.timezone)
    d = today or datetime.now(tz).date()
    title = f"⚔️ Daily Quest — {d.strftime('%B %-d, %Y')}"

    reg = Registry.load()
    records = load_records()
    prof = load_profile()
    by_cat = reg.by_category()

    lines = [
        f"<!-- irongraph:quest date={d.isoformat()} -->",
        f"### ⚔️ Daily Quest · {d.strftime('%A, %B %-d, %Y')}",
        "",
    ]
    # In GitHub Actions we know the repo — show the hero sprite in the quest
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main") or "main"
    if repo:
        lines += [
            f'<img src="https://raw.githubusercontent.com/{repo}/{branch}/generated/hero-sprite.gif" '
            'width="88" align="left" alt="your hero">',
            "",
        ]
    lines += [
        f"> **Level {prof.get('level', 1)} {prof.get('title', 'Novice')}** · "
        f"{prof.get('xp', 0)} XP · next level at {xp_for_level(prof.get('level', 1) + 1)} XP",
        "",
        '<br clear="left">' if repo else "",
        "",
        EXAMPLES,
    ]
    for cat, label in CATEGORY_META:
        exercises = sorted(by_cat.get(cat, []), key=lambda e: e.name)
        if not exercises:
            continue
        lines.append("<details>")
        lines.append(f"<summary><b>{label}</b> ({len(exercises)})</summary>")
        lines.append("")
        for ex in exercises:
            hint = _current_pr_hint(records, ex.id)
            lines.append(f"- [ ] {ex.name} :: {hint}".rstrip())
        lines.append("")
        lines.append("</details>")
        lines.append("")
    lines.append(CUSTOM_SECTION)
    lines.append(NOTES_SECTION)
    lines.append("---")
    lines.append("_Rest day? Just close the issue without checking anything — "
                 "no quest is ever failed, only postponed._ 🌙")
    return title, "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit {title, body} JSON")
    ap.add_argument("--date", help="YYYY-MM-DD override (defaults to today in configured tz)")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else None
    title, body = build_quest(today)
    if args.json:
        print(json.dumps({"title": title, "body": body}))
    else:
        print(title)
        print("---")
        print(body)


if __name__ == "__main__":
    main()
