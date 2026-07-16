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

CHEATSHEET = """\
<details>
<summary>📖 <b>Syntax cheatsheet</b></summary>

| You did | Write |
|---|---|
| 185 lb for 6 reps | `Bench Press: 185 lb x 6` |
| 3 sets of 5 at 185 | `Bench Press: 3x5 @ 185 lb` |
| bodyweight 8, then +25 lb for 5 | `Pull-ups: bw x 8; +25 lb x 5` |
| treadmill 25 min, 2.3 mi, incline 3 | `Treadmill: 25 min, 2.3 mi, incline 3` |
| incline walk, speed 3, incline 12 | `Treadmill: 30 min, speed 3, incline 12` |
| stairmaster 30 min level 8 | `StairMaster: 30 min level 8` |
| plank 2 min 15 s | `Plank: 2m15s` |
| kg instead of lb | `Squat: 84 kg x 5` |
| add a note | `Bench Press: 185 x 6 // felt strong` |
| brand-new exercise | `- [x] Sled Push [muscle: legs; equipment: sled] :: 90 lb x 30s` |

</details>
"""

# sensible fallbacks when there is no history yet for a bucket
DEFAULT_PREFILL = {
    "strength": ["Barbell Bench Press", "Lat Pulldown", "Back Squat"],
    "cardio": ["Treadmill"],
    "core": ["Cable Crunch", "Plank"],
}


def _frequent_names(registry, bucket: str, limit: int = 3) -> list[str]:
    """Owner's most-performed exercise names for a form bucket, from history."""
    from .analytics import compute_exercise_stats, load_all_events
    stats = compute_exercise_stats(load_all_events())
    def bucket_of(ex):
        if ex.category == "cardio":
            return "cardio"
        if ex.category == "core":
            return "core"
        return "strength"
    ranked = sorted(
        (s for s in stats.values() if s.times_performed > 0),
        key=lambda s: -s.times_performed)
    names = []
    for s in ranked:
        ex = registry.by_id.get(s.exercise_id)
        if ex and bucket_of(ex) == bucket:
            names.append(ex.name)
        if len(names) >= limit:
            break
    return names or DEFAULT_PREFILL[bucket]


def build_quest(today: date | None = None) -> tuple[str, str]:
    cfg = load_config()
    tz = ZoneInfo(cfg.timezone)
    d = today or datetime.now(tz).date()
    title = f"⚔️ Daily Quest — {d.strftime('%B %-d, %Y')}"

    reg = Registry.load()
    prof = load_profile()

    repo = os.environ.get("GITHUB_REPOSITORY", "ashcodex505/gym-git")
    branch = os.environ.get("GITHUB_REF_NAME", "main") or "main"
    st_names = _frequent_names(reg, "strength")
    ca_names = _frequent_names(reg, "cardio")

    lines = [
        f"<!-- irongraph:quest date={d.isoformat()} -->",
        f'<img src="https://raw.githubusercontent.com/{repo}/{branch}/generated/hero-sprite.gif" '
        'width="72" align="left" alt="your hero">',
        "",
        f"> **Level {prof.get('level', 1)} {prof.get('title', 'Novice')}** · "
        f"{prof.get('xp', 0)} XP · next level at {xp_for_level(prof.get('level', 1) + 1)} XP",
        "",
        '<br clear="left">',
        "",
        "### What did you train today?",
        "",
        f"## [📝 &nbsp;Log today's workout →](https://github.com/{repo}/issues/new?template=log-workout.yml)",
        "",
        "_Every exercise is pre-listed by muscle group — type numbers after the ones you did and Submit. "
        "New exercises you add in the dashboard appear automatically._",
        "",
        "**💬 Or comment right here, then close the issue:**",
        "",
        "```",
        f"{ca_names[0]}: 30 min, speed 3, incline 12",
        f"{st_names[0]}: 185 x 6, 185 x 5",
        "```",
        "",
        "Every `Exercise: numbers` line you comment is logged when this quest closes.",
        "",
        CHEATSHEET,
        "---",
        "_Rest day? Just close the issue — no quest is ever failed, only postponed._ 🌙",
    ]
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
