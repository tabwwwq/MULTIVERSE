"""When a macro value became available: vintages, snapshots and publication rules.

- FRED/ALFRED gives every value with its real-time period. A vintage date is a release
  day; the value counts as available from the end of that day, US Eastern time, because
  the hour of each release is not in the data (most are at 8:30 a.m.).
- World Bank values come from dated snapshots of the database (the response's
  ``lastupdated`` date): available by the end of that day, US Eastern. A year that first
  appears in a snapshot may have been published earlier; that is not evidence.
- ECB values used here are not revised, and the ECB publishes them by fixed rules:
  euro reference rates around 16:00 CET on their day; yield curves around 12:00 CET on
  the next TARGET business day; key interest rates are announced before they take
  effect, so they are known by the start of their day.

All rules err on the late side. Central European time follows the EU daylight saving
rule (last Sunday of March to last Sunday of October, at 01:00 UTC), written out here
because Windows has no time zone database in the standard library.
"""

from datetime import UTC, date, datetime, time, timedelta

from multiverse_pipelines.pit.clock import day_end

CET = timedelta(hours=1)
CEST = timedelta(hours=2)


def _last_sunday(year: int, month: int) -> date:
    following = date(year + month // 12, month % 12 + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() + 1) % 7)


def from_cet(wall: datetime) -> datetime:
    """Aware UTC moment of a naive Central European wall time."""
    if wall.year < 1996:
        raise ValueError(f"Central European time before 1996 is not supported ({wall.year})")
    start = datetime.combine(_last_sunday(wall.year, 3), time(2))
    end = datetime.combine(_last_sunday(wall.year, 10), time(3))
    offset = CEST if start <= wall < end else CET
    return (wall - offset).replace(tzinfo=UTC)


def easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return date(year, month, day)


def target_holiday(day: date) -> bool:
    """TARGET2 closing days: 1 January, Good Friday, Easter Monday, 1 May, 25 and 26 December."""
    sunday = easter(day.year)
    fixed = {(1, 1), (5, 1), (12, 25), (12, 26)}
    moving = {sunday - timedelta(days=2), sunday + timedelta(days=1)}
    return (day.month, day.day) in fixed or day in moving


def next_target_day(day: date) -> date:
    following = day + timedelta(days=1)
    while following.weekday() >= 5 or target_holiday(following):
        following += timedelta(days=1)
    return following


def vintage_available(vintage: date) -> datetime:
    """An ALFRED vintage date: available from the end of that day, US Eastern."""
    return day_end(vintage)


def snapshot_available(updated: date) -> datetime:
    """A dated World Bank snapshot: available by the end of that day, US Eastern."""
    return day_end(updated)


def h15_daily(day: date) -> datetime:
    """An H.15 daily rate: published the next business day; here the end of the second
    weekday after it, US Eastern, because US holidays are not modelled (late side)."""
    following, weekdays = day, 0
    while weekdays < 2:
        following += timedelta(days=1)
        if following.weekday() < 5:
            weekdays += 1
    return day_end(following)


def ecb_reference_rate(day: date) -> datetime:
    return from_cet(datetime.combine(day, time(16)))


def ecb_yield_curve(day: date) -> datetime:
    return from_cet(datetime.combine(next_target_day(day), time(12)))


def ecb_key_rate(day: date) -> datetime:
    return from_cet(datetime.combine(day, time.min))
