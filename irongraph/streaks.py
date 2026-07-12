"""Streak logic.

Two deliberate streak concepts (daily-forever streaks encourage skipping
recovery, so they are not the headline metric):

* activity streak — consecutive calendar days with any logged workout.
  Shown, but framed as "current run", not the primary goal.
* weekly consistency streak — consecutive ISO weeks with at least
  `weekly_consistency_target` workouts (default 3). This is the streak
  achievements care about: it rewards sustainable consistency and lets
  rest days exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Streaks:
    activity_current: int = 0
    activity_longest: int = 0
    weekly_current: int = 0
    weekly_longest: int = 0
    workouts_this_week: int = 0
    weekly_target: int = 3


def _iso_week(d: date) -> tuple[int, int]:
    c = d.isocalendar()
    return (c.year, c.week)


def compute_streaks(dates: list[str], weekly_target: int, today: str | None = None) -> Streaks:
    """`dates` = workout dates (YYYY-MM-DD, may repeat); `today` anchors currency."""
    s = Streaks(weekly_target=weekly_target)
    if not dates:
        return s
    days = sorted({date.fromisoformat(d) for d in dates})
    anchor = date.fromisoformat(today) if today else days[-1]

    # --- activity streak ------------------------------------------------
    run = 1
    longest = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    s.activity_longest = longest
    if (anchor - days[-1]).days <= 1:  # still alive today or yesterday
        run = 1
        i = len(days) - 1
        while i > 0 and (days[i] - days[i - 1]).days == 1:
            run += 1
            i -= 1
        s.activity_current = run
    # --- weekly consistency ----------------------------------------------
    per_week: dict[tuple[int, int], int] = {}
    for d in sorted(date.fromisoformat(x) for x in dates):
        per_week[_iso_week(d)] = per_week.get(_iso_week(d), 0) + 1
    s.workouts_this_week = per_week.get(_iso_week(anchor), 0)
    qualifying = {wk for wk, n in per_week.items() if n >= weekly_target}
    if qualifying:
        weeks = sorted(qualifying)
        run = 1
        longest = 1
        for pw, cw in zip(weeks, weeks[1:]):
            run = run + 1 if _next_week(pw) == cw else 1
            longest = max(longest, run)
        s.weekly_longest = longest
        # current: count back from this week or last week
        this_wk = _iso_week(anchor)
        start = this_wk if this_wk in qualifying else _prev_week(this_wk)
        if start in qualifying:
            run = 0
            wk = start
            while wk in qualifying:
                run += 1
                wk = _prev_week(wk)
            s.weekly_current = run
    return s


def _next_week(wk: tuple[int, int]) -> tuple[int, int]:
    d = date.fromisocalendar(wk[0], wk[1], 1) + timedelta(days=7)
    return _iso_week(d)


def _prev_week(wk: tuple[int, int]) -> tuple[int, int]:
    d = date.fromisocalendar(wk[0], wk[1], 1) - timedelta(days=7)
    return _iso_week(d)
