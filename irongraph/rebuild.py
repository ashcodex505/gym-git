"""Rebuild all derived state by replaying stored workout events.

data/workouts/ is the append-only source of truth; records, achievements,
profile/XP, ingestion index, graph, SVGs and README are all derived. This
tool wipes the derived files and replays every event chronologically
through the same engines the live pipeline uses — so after correcting a
stored workout (e.g. removing a mis-parsed entry), one command restores
global consistency:

    python -m irongraph.rebuild
"""

from __future__ import annotations

from . import achievements as ach
from . import gamify, paths, records
from .analytics import compute_exercise_stats, load_all_events
from .config import load_config
from .ingest import regenerate_all, save_ingested
from .models import SCHEMA_VERSION
from .registry import Registry
from .streaks import compute_streaks


def rebuild(verbose: bool = True) -> dict:
    cfg = load_config()
    registry = Registry.load()

    # ---- wipe derived state (workouts + registry are preserved) -----------
    for p in (paths.records_path(), paths.achievements_path(),
              paths.profile_path(), paths.ingested_path()):
        if p.exists():
            p.unlink()

    events = sorted(load_all_events(), key=lambda e: (e.date, e.id))
    rec = records.load_records()
    unlocked = ach.load_unlocked()
    prof = gamify.load_profile()
    issues_index: dict[str, dict] = {}
    ingested = {"schema_version": SCHEMA_VERSION, "issues": issues_index}

    prior: list = []
    total_prs = 0
    for ev in events:
        so_far = prior + [ev]
        prs = records.detect_and_apply_prs(ev, rec)
        total_prs = sum(len(h) for ex in rec["exercises"].values() for h in ex.values())

        prev_st = compute_streaks([e.date for e in prior], cfg.weekly_consistency_target, today=ev.date)
        st = compute_streaks([e.date for e in so_far], cfg.weekly_consistency_target, today=ev.date)

        patterns = set()
        for e2 in so_far:
            for en in e2.entries:
                ex = registry.by_id.get(en.exercise_id)
                if ex:
                    patterns.add(ex.movement_pattern)
        ctx = ach.Context(
            event=ev, events=so_far, prs=prs, all_pr_count=total_prs, streaks=st,
            exercise_ids_ever={en.exercise_id for e2 in so_far for en in e2.entries},
            movement_patterns_ever=patterns, stats=compute_exercise_stats(so_far))
        new_ach = ach.evaluate(ctx, unlocked)

        prior_ex_ids = {en.exercise_id for e2 in prior for en in e2.entries}
        new_ex = [en.exercise_id for en in ev.entries if en.exercise_id not in prior_ex_ids]
        gamify.award_xp(prof, workout_id=ev.id, n_exercises=len(ev.entries),
                        n_prs=len(prs), n_new_exercises=len(new_ex),
                        new_streak_weeks=max(0, st.weekly_current - prev_st.weekly_current))
        issues_index[ev.id] = {
            "date": ev.date, "ingested_at": ev.logged_at or ev.date,
            "entries": len(ev.entries), "prs": len(prs)}
        if verbose:
            names = ", ".join(en.exercise_id for en in ev.entries)
            print(f"  ✔ {ev.date} {ev.id}: {len(ev.entries)} entries ({names}) — "
                  f"{len(prs)} PRs, {len(new_ach)} achievements")
        prior = so_far

    prof["totals"] = {"workouts": len(events), "prs": total_prs,
                      "exercises_tried": len(compute_exercise_stats(events))}
    records.save_records(rec)
    ach.save_unlocked(unlocked)
    gamify.save_profile(prof)
    save_ingested(ingested)
    regenerate_all(registry)
    summary = {"events": len(events), "prs": total_prs,
               "level": prof["level"], "xp": prof["xp"]}
    if verbose:
        print(f"Rebuilt: {summary['events']} workouts · {summary['prs']} PR entries · "
              f"level {summary['level']} ({summary['xp']} XP)")
    return summary


def main() -> None:
    rebuild()


if __name__ == "__main__":
    main()
