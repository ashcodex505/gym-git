

def test_comment_logging_via_combined_body(iso_repo):
    """Comment-to-log: body has no entries, owner comment carries the workout."""
    from datetime import date

    from irongraph.ingest import ingest_issue
    from irongraph.quest import build_quest
    _t, quest_body = build_quest(date(2026, 7, 15))
    combined = quest_body + "\n\nincline treadmill: 30 min, speed 3, incline 12\nPlank: 2m 15s"
    s = ingest_issue(90, combined, date="2026-07-15")
    assert s["status"] == "ok"
    assert s["entries"] == 2


def test_close_without_logging_is_rest_day(iso_repo):
    from datetime import date

    from irongraph.ingest import ingest_issue
    from irongraph.quest import build_quest
    _t, quest_body = build_quest(date(2026, 7, 15))
    s = ingest_issue(91, quest_body, date="2026-07-15")
    assert s["status"] == "empty"
