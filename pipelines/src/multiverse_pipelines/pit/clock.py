"""EDGAR's clock: US Eastern time, and the moment a filing became public.

EDGAR's filing date is an Eastern date. A filing accepted after 5:30 p.m. (10 p.m. for
ownership forms) gets the next business day as its filing date. The submissions files
give the acceptance time in UTC: on the archived sample, filings accepted on their own
filing date cluster at 20:00-22:00 UTC (4-6 p.m. Eastern), and those accepted the
evening before their filing date at 21:00-24:00 UTC (ADR-0019).

A filing is treated as public from its acceptance, but never before the start of its
filing date: an evening filing dated the next business day belongs to that day, so a
cutoff of 31 December never sees a filing dated in January. When only the date is known,
the filing is public from the end of that day. All three choices are on the late side:
a value can arrive in a view a few hours after it was public, never before.

Windows has no time zone database in the standard library, so the Eastern offset is
computed from the US daylight saving rules (1987-2006 and since 2007).
"""

from datetime import UTC, date, datetime, time, timedelta

from multiverse_contracts.pit import TimePrecision

EST = timedelta(hours=-5)
EDT = timedelta(hours=-4)


def _sunday(year: int, month: int, nth: int) -> date:
    """The nth Sunday of a month; nth = -1 is the last one."""
    if nth > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    following = date(year + month // 12, month % 12 + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() + 1) % 7)


def daylight_saving(year: int) -> tuple[datetime, datetime]:
    """Local wall times at which daylight saving starts and ends (both at 2 a.m.)."""
    if year >= 2007:
        start, end = _sunday(year, 3, 2), _sunday(year, 11, 1)
    elif year >= 1987:
        start, end = _sunday(year, 4, 1), _sunday(year, 10, -1)
    else:
        raise ValueError(f"EDGAR time before 1987 is not supported (year {year})")
    return datetime.combine(start, time(2)), datetime.combine(end, time(2))


def offset_at(moment: datetime) -> timedelta:
    """Eastern offset from UTC at an aware moment."""
    utc = moment.astimezone(UTC).replace(tzinfo=None)
    start, end = daylight_saving(utc.year)
    # 2 a.m. standard time is 7:00 UTC; 2 a.m. daylight time is 6:00 UTC.
    return EDT if start - EST <= utc < end - EDT else EST


def to_eastern(moment: datetime) -> datetime:
    """Naive Eastern wall time of an aware moment."""
    if moment.tzinfo is None:
        raise ValueError("an EDGAR moment needs a time zone")
    return (moment.astimezone(UTC) + offset_at(moment)).replace(tzinfo=None)


def from_eastern(wall: datetime) -> datetime:
    """Aware UTC moment of a naive Eastern wall time (the repeated hour counts as daylight)."""
    start, end = daylight_saving(wall.year)
    offset = EDT if start <= wall < end else EST
    return (wall - offset).replace(tzinfo=UTC)


def eastern_date(moment: datetime) -> date:
    return to_eastern(moment).date()


def day_start(day: date) -> datetime:
    return from_eastern(datetime.combine(day, time.min))


def day_end(day: date) -> datetime:
    return from_eastern(datetime.combine(day, time.max))


def knowledge_time(filing_date: date, accepted: datetime | None) -> tuple[datetime, TimePrecision]:
    """When a filing became public, and how that was determined."""
    if accepted is None:
        return day_end(filing_date), TimePrecision.FILING_DAY_END
    local = to_eastern(accepted)
    if local.time() == time.min and local.date() == filing_date:
        # A midnight acceptance on the filing date carries the date only.
        return day_end(filing_date), TimePrecision.FILING_DAY_END
    start = day_start(filing_date)
    if accepted < start:
        return start, TimePrecision.FILING_DAY_START
    return accepted.astimezone(UTC), TimePrecision.ACCEPTED


def parse_cutoff(text: str) -> datetime:
    """A date is the end of that day in US Eastern time; a time must carry its offset."""
    try:
        return day_end(date.fromisoformat(text))
    except ValueError:
        pass
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(
            f"cutoff {text!r} has no offset: give a date or a time like 2021-12-31T16:00-05:00"
        )
    return moment.astimezone(UTC)


def stamp(moment: datetime) -> str:
    """Fixed-width UTC text that sorts like the moments it names."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def from_stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
