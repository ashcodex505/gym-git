"""Public README generator.

The README is a *view*, regenerated deterministically from data/ on every
ingestion — never the source of truth.
"""

from __future__ import annotations

from datetime import date

from .analytics import ExerciseStats
from .models import WorkoutEvent

HERO = """\
<div align="center">

# ⚒️ IronGraph

### Software evolves through commits. Strength does too.

**Every green square tells a story. Some represent code I wrote. Others represent strength I earned.**

<br>

<samp>
night falls&nbsp;&nbsp;·&nbsp;&nbsp;the forge lights&nbsp;&nbsp;·&nbsp;&nbsp;a quest opens<br>
one plain-text line becomes structured history<br>
a new best becomes a milestone, forever<br>
and the hero on the anvil below gets a little more built —<br>
one trained muscle at a time
</samp>

<br>

<a href="#physique">Physique</a> ·
<a href="#overview">Overview</a> ·
<a href="#pr-vault">PR Vault</a> ·
<a href="#quest-log">Quest Log</a> ·
<a href="#progression">Progression</a> ·
<a href="#muscles">Muscles</a> ·
<a href="#trophies">Trophies</a> ·
<a href="#philosophy">How it works</a>

</div>

---
"""

PHILOSOPHY = """\
## <img src="generated/sprites/forge.gif" width="30" alt=""> The Forge — Contribution Philosophy

| Software | Strength |
|---|---|
| Issues | Daily workout quests |
| Commits | Completed training sessions |
| Version history | Physical progression |
| Releases | Major personal-record milestones |
| Dependency graph | The exercise knowledge graph |
| Contribution graph | Code **and** real-world training, side by side |

> You write code to improve software. You train to improve yourself.
> **IronGraph gives both forms of progress a version history.**

**How it works:** at 9 PM (America/Phoenix) a GitHub Action opens a quest
issue — a blank prompt, nothing pre-filled, nothing to pick from. I edit
the issue (or just comment) with what I did, in my own words, and close
it. A workflow matches each exercise name — exactly, then fuzzily, typos
and all — against everything I've ever trained; a name that still
doesn't match becomes a brand-new exercise on the spot. It parses and
validates the numbers, updates records, achievements, charts, and **the
hero's physique** (see above), and creates **one atomic Git commit
authored as `Ashish Kurse <ashishkurse@gmail.com>`** on the default
branch — so when GitHub's
[documented contribution criteria](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/managing-contribution-settings-on-your-profile/why-are-my-contributions-not-showing-up-on-my-profile)
are satisfied, a workout can appear on my contribution graph exactly like
code. GitHub Actions is only the scribe; the author of the workout — and
of the strength — is me.

<details>
<summary>Why fuzzy matching, and why the hero has a physique at all</summary>

<br>

Two design choices that aren't obvious from the diagrams above:

- **Matching is deliberately conservative.** A typo like "Deadlft" finds
  "Deadlift" instantly, but a bare, ambiguous word like "Press" or
  "Squat" is *never* auto-matched to one variant over another — ties
  between two genuinely different exercises are left unresolved, so a
  new exercise is created instead of silently crediting the wrong lift.
  Better an extra graph node than a corrupted PR history.
- **The hero's regions grow independently**, driven by how often *that
  region specifically* has been trained — not overall level. A
  deadlift-only lifter and a bench-only lifter end up visibly different
  at the same level, because they are.

</details>

<sub>No claim is made that every automated commit is guaranteed a green
square — attribution ultimately follows GitHub's own rules. IronGraph's
job is to make each workout commit *eligible*: real repository, default
branch, my verified email as author.</sub>
"""

FOOTER = """\
---

## 🛠️ Under the Hood

- **[Architecture](docs/architecture.md)** — how an issue becomes a commit
- **[Setup guide](docs/setup.md)** — run your own IronGraph
- **[Data schemas](docs/data-schema.md)** — everything is auditable JSON
- **[Contribution attribution](docs/contribution-attribution.md)** — why the author is a human, not a bot
- **[Local dashboard](docs/dashboard.md)** — the Obsidian-like exercise graph (`make dev`)
- **[AI integration](docs/ai.md)** — optional Gemini-powered coach

<div align="center">
<sub>Built with IronGraph — <b>Build strength. Commit progress.</b>
Training data is personal history, not medical advice.</sub>
</div>
"""


def _fmt_dur_min(s: float) -> str:
    return f"{int(round(s / 60))} min"


def _recent_activity(events: list[WorkoutEvent], n: int = 7) -> str:
    lines = ['<a id="quest-log"></a>',
             '## <img src="generated/sprites/scroll.gif" width="26" alt=""> Quest Log', ""]
    if not events:
        lines.append("_The quest log is empty. Tonight's quest awaits._ ⚔️")
        return "\n".join(lines) + "\n"
    lines.append("| Date | Session | Highlights |")
    lines.append("|---|---|---|")
    for ev in list(reversed(events))[:n]:
        highlights = []
        for e in ev.entries[:3]:
            bw = e.best_weight_set()
            if bw and bw.weight_lb() is not None:
                highlights.append(f"{e.exercise_name} {bw.weight:g} {bw.unit or 'lb'} × {bw.reps or '—'}")
            elif e.total_distance_mi():
                highlights.append(f"{e.exercise_name} {e.total_distance_mi():.1f} mi")
            elif e.total_duration_s():
                highlights.append(f"{e.exercise_name} {_fmt_dur_min(e.total_duration_s())}")
            else:
                br = e.best_reps_set()
                highlights.append(f"{e.exercise_name}" + (f" × {br.reps}" if br and br.reps else ""))
        more = f" +{len(ev.entries) - 3} more" if len(ev.entries) > 3 else ""
        lines.append(f"| {ev.date} | {ev.workout_type} | {', '.join(highlights)}{more} |")
    return "\n".join(lines) + "\n"


# body region -> tier-0..4 flavor line, keyed to the exact thresholds in
# analytics.MUSCLE_TIER_THRESHOLDS so the copy never drifts from the math
_PHYSIQUE_FLAVOR = ["still finding its shape", "just getting started",
                   "visibly building", "genuinely jacked", "an absolute unit"]


def _physique_section(muscle_tiers: dict[str, int]) -> str:
    tiers = muscle_tiers or {}
    regions = ["shoulders", "chest", "back", "arms", "core", "legs"]
    trained = [r for r in regions if tiers.get(r, 0) > 0]
    if not trained:
        callout = "_Nothing trained yet — the hero is a blank slate. Log a workout and watch a region wake up._"
    else:
        leader = max(regions, key=lambda r: tiers.get(r, 0))
        callout = (f"**{leader.capitalize()}** is furthest along right now — "
                   f"{_PHYSIQUE_FLAVOR[min(tiers.get(leader, 0), 4)]}.")
    return (
        '<a id="physique"></a>\n'
        '## 💪 Physique — the hero is built by what you train\n\n'
        "No two lifters look the same, and neither do their heroes. Every region below "
        "grows **independently**, in real pixels, on the sprite above — skip leg day "
        "and the hero's legs will, visibly, know.\n\n"
        '<div align="center">\n\n'
        '<img src="generated/physique.svg" alt="Physique — per-region training tiers" width="860">\n\n'
        "</div>\n\n"
        f"{callout}\n"
    )


def build_readme(*, stats_summary: dict, events: list[WorkoutEvent],
                 ex_stats: dict[str, ExerciseStats], registry,
                 featured_charts: list[str],
                 muscle_tiers: dict[str, int] | None = None) -> str:
    parts = [HERO]

    level = stats_summary.get("level", 1)
    title = stats_summary.get("title", "Novice")
    xp = stats_summary.get("xp", 0)
    # Terraria-style HUD: hearts = quests this week, mana stars = level progress
    week = stats_summary.get("workouts_this_week", 0)
    target = stats_summary.get("weekly_target", 3)
    hearts = "".join(
        f'<img src="generated/sprites/{"heart" if i < week else "heart-empty"}.gif" width="20" alt="">'
        for i in range(max(target, week)))
    from .gamify import xp_for_level as _xfl
    floor_xp, next_xp = _xfl(level), _xfl(level + 1)
    frac = (xp - floor_xp) / max(next_xp - floor_xp, 1)
    stars = "".join(
        f'<img src="generated/sprites/{"star" if i < round(frac * 5) else "star-empty"}.gif" width="20" alt="">'
        for i in range(5))
    parts.append(
        '<div align="center">\n\n'
        f'<img src="generated/scene.gif" alt="The IronGraph hero training at the forge, level {level} {title}" width="410">\n\n'
        f"**⚔️ Level {level} · {title}** — {xp} XP\n\n"
        f'{hearts}&nbsp;&nbsp;&nbsp;{stars}\n\n'
        f"<sub>❤️ quests this week ({week}/{target}) · ✦ progress to level {level + 1}</sub>\n\n"
        "<sub>Gear is forged by consistency: cloth → leather → steel → gilded → ember, one tier per milestone level.\n"
        "Physique is forged by specificity — see below. Every workout commit is XP; every PR re-lights the forge.</sub>\n\n"
        "</div>\n"
    )

    parts.append(_physique_section(muscle_tiers or {}))

    parts.append(
        '<a id="overview"></a>\n'
        '## 📈 Strength Overview\n\n'
        '<div align="center">\n\n'
        '<img src="generated/strength-overview.svg" alt="Strength overview" width="860">\n\n'
        '<img src="generated/workout-heatmap.svg" alt="Training heatmap" width="860">\n\n'
        "</div>\n"
    )

    parts.append('<a id="pr-vault"></a>\n'
                 '## <img src="generated/sprites/trophy.gif" width="26" alt=""> PR Vault\n\n'
                 "Every record below was once impossible.\n\n"
                 '<img src="generated/personal-records.svg" alt="Personal records" width="860">\n')

    parts.append(_recent_activity(events))

    if featured_charts:
        chart_md = ['<a id="progression"></a>',
                    '## <img src="generated/sprites/sword.gif" width="22" alt=""> Strength Progression\n']
        for slug in featured_charts:
            chart_md.append(f'<img src="generated/exercises/{slug}.svg" alt="{slug} progression" width="860">\n')
        parts.append("\n".join(chart_md))

    parts.append('<a id="muscles"></a>\n'
                 "## 🫀 Attribute Distribution\n\n"
                 '<img src="generated/muscle-distribution.svg" alt="Muscle distribution" width="860">\n')

    parts.append('<a id="trophies"></a>\n'
                 '## <img src="generated/sprites/chest.gif" width="28" alt=""> Trophy Hall\n\n'
                 '<img src="generated/achievements.svg" alt="Achievements" width="860">\n')

    parts.append('<a id="philosophy"></a>\n' + PHILOSOPHY)
    parts.append(FOOTER)
    parts.append(f"\n<sub>README generated {date.today().isoformat()} from"
                 f" {stats_summary.get('total_workouts', 0)} recorded workouts."
                 " Data lives in <code>data/</code>; every number is recomputable.</sub>\n")
    return "\n".join(parts)
