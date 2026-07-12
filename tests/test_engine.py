"""PR engine, e1RM, streaks, achievements, gamification."""

from irongraph import records
from irongraph.analytics import epley_e1rm
from irongraph.gamify import level_from_xp, title_for_level, xp_for_level
from irongraph.models import SetRecord, WorkoutEntry, WorkoutEvent
from irongraph.streaks import compute_streaks


def ev(date, entries, id=None):
    return WorkoutEvent(id=id or f"issue-{date}", date=date, entries=entries)


def bench(w, r, unit="lb"):
    return WorkoutEntry(exercise_id="barbell-bench-press", exercise_name="Barbell Bench Press",
                        modality="weight_reps", sets=[SetRecord(weight=w, unit=unit, reps=r)])


def test_epley():
    assert epley_e1rm(185, 1, max_reps=12) == 185
    assert abs(epley_e1rm(185, 6, max_reps=12) - 222.0) < 0.1
    assert epley_e1rm(100, 13, max_reps=12) is None
    assert epley_e1rm(100, 0, max_reps=12) is None


def test_first_workout_sets_prs(iso_repo):
    rec = records.load_records()
    prs = records.detect_and_apply_prs(ev("2026-07-12", [bench(185, 6)]), rec)
    types = {p.record_type for p in prs}
    assert "max_weight" in types and "max_e1rm" in types and "rep_weight:6" in types
    pr = next(p for p in prs if p.record_type == "max_weight")
    assert pr.previous_display is None and pr.value == 185


def test_pr_progression_and_no_pr(iso_repo):
    rec = records.load_records()
    records.detect_and_apply_prs(ev("2026-07-12", [bench(180, 6)]), rec)
    prs2 = records.detect_and_apply_prs(ev("2026-07-14", [bench(185, 6)], id="issue-2"), rec)
    w = next(p for p in prs2 if p.record_type == "max_weight")
    assert w.previous_display == "180 lb × 6" and w.delta_display == "+5 lb"
    # lower weight later: no max_weight PR
    prs3 = records.detect_and_apply_prs(ev("2026-07-16", [bench(175, 6)], id="issue-3"), rec)
    assert not any(p.record_type == "max_weight" for p in prs3)
    # history preserved
    hist = rec["exercises"]["barbell-bench-press"]["max_weight"]
    assert [h["value"] for h in hist] == [180, 185]


def test_kg_normalization_in_prs(iso_repo):
    rec = records.load_records()
    records.detect_and_apply_prs(ev("2026-07-12", [bench(185, 5)]), rec)
    # 85 kg = 187.4 lb → PR
    prs = records.detect_and_apply_prs(ev("2026-07-13", [bench(85, 5, unit="kg")], id="issue-2"), rec)
    assert any(p.record_type == "max_weight" for p in prs)


def test_bodyweight_and_cardio_records(iso_repo):
    rec = records.load_records()
    pullups = WorkoutEntry(exercise_id="pull-up", exercise_name="Pull-ups", modality="reps",
                           sets=[SetRecord(reps=8), SetRecord(weight=25, unit="lb", reps=5, added_weight=True)])
    run = WorkoutEntry(exercise_id="outdoor-run", exercise_name="Outdoor Run", modality="distance_time",
                       sets=[SetRecord(duration_s=1725, distance=3.2, distance_unit="mi")])
    prs = records.detect_and_apply_prs(ev("2026-07-12", [pullups, run]), rec)
    types = {(p.exercise_id, p.record_type) for p in prs}
    assert ("pull-up", "max_reps") in types
    assert ("pull-up", "max_added") in types
    assert ("outdoor-run", "max_distance") in types
    assert ("outdoor-run", "best_pace") in types
    pace = next(p for p in prs if p.record_type == "best_pace")
    assert pace.display.startswith("8:")   # 1725/3.2 ≈ 539 s/mi ≈ 8:59


def test_short_cardio_gets_no_pace_record(iso_repo):
    rec = records.load_records()
    walk = WorkoutEntry(exercise_id="walking", exercise_name="Walking", modality="distance_time",
                        sets=[SetRecord(duration_s=300, distance=0.4, distance_unit="mi")])
    prs = records.detect_and_apply_prs(ev("2026-07-12", [walk]), rec)
    assert not any(p.record_type == "best_pace" for p in prs)


def test_streaks_weekly_and_activity():
    # 3 workouts/week for 3 ISO weeks (Mon/Wed/Fri), then check
    dates = ["2026-06-15", "2026-06-17", "2026-06-19",
             "2026-06-22", "2026-06-24", "2026-06-26",
             "2026-06-29", "2026-07-01", "2026-07-03"]
    s = compute_streaks(dates, weekly_target=3, today="2026-07-03")
    assert s.weekly_current == 3 and s.weekly_longest == 3
    assert s.activity_current == 1
    # consecutive days
    s2 = compute_streaks(["2026-07-01", "2026-07-02", "2026-07-03"], 3, today="2026-07-03")
    assert s2.activity_current == 3 and s2.activity_longest == 3
    # broken activity streak (anchor 3 days later)
    s3 = compute_streaks(["2026-07-01", "2026-07-02"], 3, today="2026-07-06")
    assert s3.activity_current == 0 and s3.activity_longest == 2


def test_streak_gap_resets_weekly():
    dates = ["2026-06-01", "2026-06-03", "2026-06-05",     # qualifying week
             "2026-06-22", "2026-06-24", "2026-06-26"]     # gap, then qualifying
    s = compute_streaks(dates, 3, today="2026-06-26")
    assert s.weekly_current == 1 and s.weekly_longest == 1


def test_levels():
    assert xp_for_level(1) == 0
    assert level_from_xp(0) == 1
    assert level_from_xp(250) == 2
    assert level_from_xp(749) == 2
    assert level_from_xp(750) == 3
    assert title_for_level(1) == "Novice"
    assert title_for_level(10) == "Ironbound"
    assert title_for_level(31) == "Titan"
