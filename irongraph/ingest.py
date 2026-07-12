"""Workout ingestion pipeline (the heart of IronGraph).

    issue body ──► parse ──► validate ──► WorkoutEvent (append-only)
                                    │
        ┌────────────┬──────────────┼──────────────┬─────────────┐
        ▼            ▼              ▼              ▼             ▼
     PR engine   achievements   XP/streaks    graph.json   SVGs + README

Everything lands in the working tree; the workflow then makes ONE atomic
commit authored by the configured human. Idempotent: an issue id that was
already ingested is a no-op (exit code 3) — never a duplicate workout.

CLI:
    python -m irongraph.ingest --issue-number 42 --issue-body-file body.md \
        [--date 2026-07-12] [--issue-url URL] [--summary-file out.json]

Exit codes: 0 ok · 2 validation failed (details in summary file) · 3 duplicate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import achievements as ach
from . import gamify, graphbuild, paths, records, svggen
from .analytics import compute_exercise_stats, load_all_events, muscle_distribution
from .commitmsg import build_body, build_subject
from .config import load_config
from .models import SCHEMA_VERSION, WorkoutEvent
from .parser import QuestParser
from .readmegen import build_readme
from .registry import Registry
from .streaks import compute_streaks

FEATURED = ["barbell-bench-press", "back-squat", "deadlift", "overhead-press",
            "lat-pulldown", "pull-up"]


def load_ingested() -> dict:
    p = paths.ingested_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"schema_version": SCHEMA_VERSION, "issues": {}}


def save_ingested(d: dict) -> None:
    paths.ingested_path().parent.mkdir(parents=True, exist_ok=True)
    paths.ingested_path().write_text(json.dumps(d, indent=2) + "\n")


def regenerate_all(registry: Registry | None = None) -> dict:
    """Rebuild every derived artifact (graph, SVGs, README) from data/.
    Deterministic; callable standalone via `python -m irongraph.ingest --regen`."""
    cfg = load_config()
    registry = registry or Registry.load()
    events = load_all_events()
    ex_stats = compute_exercise_stats(events)
    rec = records.load_records()
    unlocked = ach.load_unlocked()
    prof = gamify.load_profile()

    all_dates = [ev.date for ev in events]
    st = compute_streaks(all_dates, cfg.weekly_consistency_target,
                         today=datetime.now(ZoneInfo(cfg.timezone)).date().isoformat())
    prof["streaks"] = {
        "activity_current": st.activity_current, "activity_longest": st.activity_longest,
        "weekly_current": st.weekly_current, "weekly_longest": st.weekly_longest,
        "workouts_this_week": st.workouts_this_week, "weekly_target": st.weekly_target,
    }

    # every history entry was a PR at the moment it was set
    total_prs = sum(len(h) for ex in rec["exercises"].values() for h in ex.values())
    summary = {
        "as_of": events[-1].date if events else "",
        "total_workouts": len(events),
        "total_prs": total_prs,
        "exercises_tried": len(ex_stats),
        "activity_current": st.activity_current,
        "activity_longest": st.activity_longest,
        "weekly_current": st.weekly_current,
        "workouts_this_week": st.workouts_this_week,
        "weekly_target": st.weekly_target,
        "level": prof.get("level", 1),
        "title": prof.get("title", "Novice"),
        "xp": prof.get("xp", 0),
    }

    # ---- graph ----------------------------------------------------------
    recent_pr_ids = set()
    if events:
        recent_dates = {ev.date for ev in events[-5:]}
        for ex_id, kinds in rec["exercises"].items():
            for hist in kinds.values():
                if hist and hist[-1]["date"] in recent_dates:
                    recent_pr_ids.add(ex_id)
    graph = graphbuild.build_graph(registry, ex_stats, pr_recent=recent_pr_ids)
    graphbuild.write_graph(graph)

    # ---- SVGs -----------------------------------------------------------
    day_counts: dict[str, int] = {}
    for ev in events:
        day_counts[ev.date] = day_counts.get(ev.date, 0) + len(ev.entries)
    svggen.write("strength-overview.svg", svggen.strength_overview(summary))
    from datetime import date as _date
    heat_end = _date.today()
    if events:
        heat_end = max(heat_end, _date.fromisoformat(events[-1].date))
    svggen.write("workout-heatmap.svg", svggen.workout_heatmap(day_counts, end=heat_end))
    pr_rows = []
    for ex_id in FEATURED + [i for i in ex_stats if i not in FEATURED]:
        stx = ex_stats.get(ex_id)
        exd = registry.by_id.get(ex_id)
        if not stx or not exd:
            continue
        if stx.best_weight_lb:
            disp = f"{stx.best_weight_lb:g} lb" + (f" × {stx.best_weight_reps}" if stx.best_weight_reps else "")
            e1 = f"~{stx.best_e1rm:g} lb e1RM" if stx.best_e1rm else ""
        elif stx.best_reps:
            disp = f"{stx.best_reps} reps"
            e1 = (f"+{stx.best_added_lb:g} lb × {stx.best_added_reps}" if stx.best_added_lb else "")
        elif stx.best_distance_mi:
            disp = f"{stx.best_distance_mi:.2f} mi"
            e1 = f"best pace {int(stx.best_pace_s_per_mi // 60)}:{int(stx.best_pace_s_per_mi % 60):02d}/mi" if stx.best_pace_s_per_mi else ""
        elif stx.best_duration_s:
            disp, e1 = records._fmt_dur(stx.best_duration_s), ""
        else:
            continue
        pr_rows.append({"name": exd.name, "display": disp, "e1rm": e1})
    svggen.write("personal-records.svg", svggen.personal_records_card(pr_rows))
    svggen.write("muscle-distribution.svg", svggen.muscle_distribution(muscle_distribution(events, registry)))
    svggen.write("achievements.svg", svggen.achievements_card(unlocked["unlocked"], len(ach.ACHIEVEMENTS)))

    # ---- pixel world: level-tier hero + full sprite library ---------------
    from .sprites import generate_all
    generate_all(prof.get("level", 1), paths.generated_dir())

    featured_charts = []
    for ex_id, stx in ex_stats.items():
        exd = registry.by_id.get(ex_id)
        if not exd or not stx.history:
            continue
        chart = svggen.exercise_progression(exd.name, stx.history)
        if chart:
            svggen.write(f"{ex_id}.svg", chart, subdir="exercises")
            if ex_id in FEATURED:
                featured_charts.append(ex_id)
    featured_charts.sort(key=lambda x: FEATURED.index(x))
    if not featured_charts:  # fall back to any exercise with a chart
        featured_charts = [i for i in ex_stats if (paths.generated_dir() / "exercises" / f"{i}.svg").exists()][:3]

    # ---- README ----------------------------------------------------------
    readme = build_readme(stats_summary=summary, events=events, ex_stats=ex_stats,
                          registry=registry, featured_charts=featured_charts)
    (paths.repo_root() / "README.md").write_text(readme)
    gamify.save_profile(prof)
    return summary


def ingest_issue(issue_number: int, issue_body: str, *, date: str | None = None,
                 issue_url: str = "") -> dict:
    """Full pipeline for one quest issue. Returns a summary dict."""
    cfg = load_config()
    ingested = load_ingested()
    key = f"issue-{issue_number}"
    if key in ingested["issues"]:
        return {"status": "duplicate", "message":
                f"Issue #{issue_number} was already recorded on "
                f"{ingested['issues'][key]['ingested_at'][:10]} — nothing to do. 💤"}

    registry = Registry.load()
    parser = QuestParser(registry, default_unit=cfg.default_weight_unit)
    result = parser.parse(issue_body)
    if result.problems:
        return {"status": "invalid",
                "problems": [p.reason for p in result.problems],
                "message": "Some lines couldn't be understood — nothing was recorded."}

    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    wdate = date or now.date().isoformat()
    event = WorkoutEvent(
        id=key, date=wdate, entries=result.entries,
        source={"type": "github-issue", "issue_number": issue_number, "issue_url": issue_url},
        logged_at=now.isoformat(timespec="seconds"),
        notes=result.session_notes if cfg.privacy.get("publish_notes", True) else None,
    )

    # ---- persist the event (append-only) ---------------------------------
    year_dir = paths.workouts_dir() / wdate[:4]
    year_dir.mkdir(parents=True, exist_ok=True)
    event_path = year_dir / f"{wdate}--{key}.json"
    event_path.write_text(json.dumps(event.to_dict(), indent=2) + "\n")

    # ---- history-derived context -----------------------------------------
    events = load_all_events()
    ex_stats = compute_exercise_stats(events)
    prior_events = [e for e in events if e.id != key]
    prior_ex_ids = {en.exercise_id for ev in prior_events for en in ev.entries}

    # ---- PRs --------------------------------------------------------------
    rec = records.load_records()
    prs = records.detect_and_apply_prs(event, rec)
    records.save_records(rec)
    total_prs = sum(len(h) for ex in rec["exercises"].values() for h in ex.values())

    # ---- streaks ----------------------------------------------------------
    prev_st = compute_streaks([e.date for e in prior_events], cfg.weekly_consistency_target, today=wdate)
    st = compute_streaks([e.date for e in events], cfg.weekly_consistency_target, today=wdate)
    new_streak_weeks = max(0, st.weekly_current - prev_st.weekly_current)

    # ---- achievements ------------------------------------------------------
    patterns = set()
    for ev in events:
        for en in ev.entries:
            ex = registry.by_id.get(en.exercise_id)
            if ex:
                patterns.add(ex.movement_pattern)
    ctx = ach.Context(event=event, events=events, prs=prs, all_pr_count=total_prs,
                      streaks=st, exercise_ids_ever={en.exercise_id for ev in events for en in ev.entries},
                      movement_patterns_ever=patterns, stats=ex_stats)
    unlocked = ach.load_unlocked()
    new_ach = ach.evaluate(ctx, unlocked)
    ach.save_unlocked(unlocked)

    # ---- XP ---------------------------------------------------------------
    prof = gamify.load_profile()
    new_ex = [en.exercise_id for en in event.entries if en.exercise_id not in prior_ex_ids]
    grants = gamify.award_xp(prof, workout_id=key, n_exercises=len(event.entries),
                             n_prs=len(prs), n_new_exercises=len(new_ex),
                             new_streak_weeks=new_streak_weeks)
    prof["totals"]["workouts"] = len(events)
    prof["totals"]["prs"] = total_prs
    prof["totals"]["exercises_tried"] = len(ex_stats)
    gamify.save_profile(prof)

    # ---- mark ingested BEFORE regenerating views --------------------------
    ingested["issues"][key] = {"date": wdate, "ingested_at": now.isoformat(timespec="seconds"),
                               "entries": len(event.entries), "prs": len(prs)}
    save_ingested(ingested)

    regenerate_all(registry)

    # ---- commit message ----------------------------------------------------
    streak_line = None
    if st.weekly_current >= 2:
        streak_line = (f"Weekly consistency streak: {st.weekly_current} weeks at "
                       f"{cfg.weekly_consistency_target}+ workouts/week")
    elif st.activity_current >= 3:
        streak_line = f"{st.activity_current}-day activity streak"
    subject = build_subject(event, prs)
    body = build_body(event, prs, new_ach, grants, cfg.git_author.name,
                      cfg.git_author.email, streak_line)

    return {
        "status": "ok", "workout_id": key, "date": wdate,
        "entries": len(event.entries), "prs": [
            {"exercise": p.exercise_name, "type": p.record_type, "display": p.display,
             "previous": p.previous_display, "delta": p.delta_display} for p in prs],
        "achievements": [{"id": a.id, "name": a.name, "emoji": a.emoji} for a in new_ach],
        "xp": grants, "level": prof["level"], "title": prof["title"],
        "new_custom_exercises": result.new_custom,
        "commit_subject": subject, "commit_body": body,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--issue-number", type=int)
    ap.add_argument("--issue-body-file")
    ap.add_argument("--issue-url", default="")
    ap.add_argument("--date")
    ap.add_argument("--summary-file", help="write the result summary JSON here")
    ap.add_argument("--regen", action="store_true", help="only regenerate derived views")
    args = ap.parse_args()

    if args.regen:
        s = regenerate_all()
        print(json.dumps(s, indent=2))
        return

    if args.issue_number is None or not args.issue_body_file:
        ap.error("--issue-number and --issue-body-file are required (or use --regen)")
    body = open(args.issue_body_file, encoding="utf-8").read()
    summary = ingest_issue(args.issue_number, body, date=args.date, issue_url=args.issue_url)
    out = json.dumps(summary, indent=2)
    print(out)
    if args.summary_file:
        open(args.summary_file, "w").write(out)
    if summary["status"] == "invalid":
        sys.exit(2)
    if summary["status"] == "duplicate":
        sys.exit(3)


if __name__ == "__main__":
    main()
