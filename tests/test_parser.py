from conftest import fixture

from irongraph.parser import QuestParser
from irongraph.registry import Registry


def make_parser(iso_repo):
    return QuestParser(Registry.load(), default_unit="lb")


def test_strength_day(iso_repo):
    res = make_parser(iso_repo).parse(fixture("strength_day.md"))
    assert res.ok
    ids = [e.exercise_id for e in res.entries]
    assert ids == ["barbell-bench-press", "lat-pulldown", "incline-dumbbell-press", "cable-fly"]
    bench = res.entries[0]
    assert [s.weight for s in bench.sets] == [185.0, 185.0]
    assert [s.reps for s in bench.sets] == [6, 5]
    assert bench.notes == "paused reps"
    assert len(res.entries[1].sets) == 3          # 160 lb x 8 x 3 => 3 sets
    assert len(res.entries[3].sets) == 3          # 3x12 @ 42.5 lb
    assert res.entries[3].sets[0].weight == 42.5
    assert res.session_notes == "Chest and back day, felt strong."


def test_unchecked_ignored(iso_repo):
    res = make_parser(iso_repo).parse(fixture("strength_day.md"))
    assert "deadlift" not in [e.exercise_id for e in res.entries]


def test_cardio_day(iso_repo):
    res = make_parser(iso_repo).parse(fixture("cardio_day.md"))
    assert res.ok
    tm = res.entries[0].sets[0]
    assert tm.duration_s == 1500
    assert tm.distance == 2.3 and tm.distance_unit == "mi"
    assert tm.incline_pct == 3.0
    sm = res.entries[1].sets[0]
    assert sm.duration_s == 1800 and sm.level == 8


def test_abs_day(iso_repo):
    res = make_parser(iso_repo).parse(fixture("abs_day.md"))
    assert res.ok
    crunch, hlr, plank = res.entries
    assert crunch.sets[0].weight == 110 and len(crunch.sets) == 3
    assert [s.reps for s in hlr.sets] == [15, 12, 10]
    assert [s.weight for s in hlr.sets] == [None, None, None]
    assert [s.duration_s for s in plank.sets] == [135, 100]


def test_mixed_day_weighted_bodyweight_and_rpe(iso_repo):
    res = make_parser(iso_repo).parse(fixture("mixed_day.md"))
    assert res.ok
    squat, pullups, run = res.entries
    assert squat.sets[-1].rpe == 8.5
    assert pullups.sets[0].weight is None and pullups.sets[0].reps == 8
    assert pullups.sets[1].added_weight and pullups.sets[1].weight == 25
    assert run.sets[0].distance == 3.2
    assert run.sets[0].duration_s == 28 * 60 + 45


def test_malformed_rejected_with_reasons(iso_repo):
    res = make_parser(iso_repo).parse(fixture("malformed.md"))
    assert not res.ok
    assert len(res.problems) == 2
    assert not res.entries  # bench failed AND treadmill failed


def test_custom_exercise_registration(iso_repo):
    p = make_parser(iso_repo)
    res = p.parse(fixture("custom_exercise.md"))
    assert res.ok
    assert res.new_custom == ["landmine-press", "nordic-curl"]
    lp = p.registry.by_id["landmine-press"]
    assert lp.category == "shoulders" and lp.equipment == "barbell" and lp.custom
    nc = p.registry.by_id["nordic-curl"]
    assert nc.modality == "reps"
    # persisted: a fresh registry load still knows it
    assert Registry.load().resolve("landmine press") is not None


def test_kg_units(iso_repo):
    res = make_parser(iso_repo).parse(fixture("kg_day.md"))
    assert res.ok
    ohp = res.entries[0].sets[0]
    assert ohp.weight == 84 and ohp.unit == "kg"
    assert abs((ohp.weight_lb() or 0) - 185.19) < 0.1
    curls = res.entries[1]
    assert len(curls.sets) == 2 and curls.sets[0].unit == "kg"


def test_empty_body(iso_repo):
    res = make_parser(iso_repo).parse("nothing here")
    assert not res.ok and res.problems


def test_alias_resolution(iso_repo):
    r = Registry.load()
    assert r.resolve("bench press").id == "barbell-bench-press"
    assert r.resolve("Push ups").id == "push-up"
    assert r.resolve("RDL").id == "romanian-deadlift"
    assert r.resolve("ohp").id == "overhead-press"


def test_fuzzy_resolution_typo_tolerant(iso_repo):
    r = Registry.load()
    assert r.resolve_fuzzy("Deadlft").id == "deadlift"
    assert r.resolve_fuzzy("Treadmil").id == "treadmill"


def test_fuzzy_resolution_never_confuses_different_exercises(iso_repo):
    """A 2026-07 near-miss: naive character-similarity matched "Landmine
    Press" to "Standing Press" (an Overhead Press alias) purely because
    both strings share "press". Distinct lifts must never be confused."""
    r = Registry.load()
    assert r.resolve_fuzzy("landmine press") is None
    assert r.resolve_fuzzy("nordic curl") is None
    # generic single words shared by several variants must stay ambiguous
    assert r.resolve_fuzzy("press") is None


def test_freeform_ignores_prose_with_dashes_or_colons(iso_repo):
    """A 2026-07 incident: closing a quest issue posts an owner comment
    like "Superseded by the redesign — quest logging is now freeform" —
    the em dash must never be misread as a workout separator and fail
    validation just because it's prose, not a logged exercise."""
    res = make_parser(iso_repo).parse(
        "Superseded by the app redesign — quest logging is now freeform "
        "plaintext (no checkbox menu). Closing this old-style quest issue.\n"
        "Note: felt tired today, took it easy.\n"
    )
    assert not res.entries
    # treated as a no-op ("rest day"), never a validation failure
    assert len(res.problems) == 1 and res.problems[0].line == ""


def test_freeform_plaintext_no_checkbox_needed(iso_repo):
    """The redesigned quest issue has no checkbox wall or pre-listed
    exercise menu — bare `Exercise: numbers` lines must log on their own,
    and casual/typo'd names still land on the right exercise."""
    res = make_parser(iso_repo).parse(
        "Bench Press: 185 lb x 6, 185 x 5\n"
        "Deadlft: 315 x 3\n"
        "Sled Push: 90 lb x 20\n"
    )
    ids = [e.exercise_id for e in res.entries]
    assert "barbell-bench-press" in ids
    assert "deadlift" in ids
    assert "sled-push" in ids
    assert "sled-push" in res.new_custom


def test_incline_speed_walk(iso_repo):
    p = make_parser(iso_repo)
    res = p.parse("- [x] Treadmill :: 25 min, speed 3, incline 12")
    assert res.ok
    s = res.entries[0].sets[0]
    assert s.duration_s == 1500 and s.speed == 3.0 and s.incline_pct == 12.0
    # distance derived from speed × time (3 mph × 25 min = 1.25 mi)
    assert s.distance == 1.25 and s.distance_unit == "mi" and s.distance_derived


def test_mph_not_confused_with_miles(iso_repo):
    p = make_parser(iso_repo)
    res = p.parse("- [x] Treadmill :: 30 min 3.5 mph incline 10")
    assert res.ok
    s = res.entries[0].sets[0]
    assert s.speed == 3.5 and s.incline_pct == 10.0
    assert s.distance == 1.75  # derived, not parsed as miles


def test_explicit_distance_wins_over_derivation(iso_repo):
    p = make_parser(iso_repo)
    res = p.parse("- [x] Treadmill :: 25 min, 2.3 mi, speed 5.5, incline 3")
    s = res.entries[0].sets[0]
    assert s.distance == 2.3 and s.speed == 5.5 and not s.distance_derived


def test_code_fences_are_never_parsed(iso_repo):
    """Syntax examples inside ``` fences must not become workout entries
    (the phantom 'Landmine Press' bug from the first real quest)."""
    p = make_parser(iso_repo)
    res = p.parse("""### How to log
```
- [x] Landmine Press [muscle: shoulders] :: 70 lb x 10
Barbell Bench Press: 999 lb x 1
```
- [x] Treadmill :: 30 min, speed 3, incline 12
""")
    assert res.ok
    assert [e.exercise_id for e in res.entries] == ["treadmill"]


def test_full_quest_template_parses_to_zero_entries(iso_repo):
    """The untouched quest issue template must contain NOTHING loggable."""
    from datetime import date

    from irongraph.quest import build_quest
    p = make_parser(iso_repo)
    _title, body = build_quest(date(2026, 7, 12))
    res = p.parse(body)
    assert res.entries == []
