"""SYNTHETIC macro documents in the shape of ALFRED, ECB and World Bank responses.

No value here is real. The documents exist so that the parsers, the vintage store and
the as-of join run end to end before the owner's decisions D-11 (FRED key) and D-12
(ECB, World Bank) allow real downloads. Every observation built from them is marked
``synthetic``, and the join writes them to a separate folder.

The publication patterns are realistic on purpose, because they are what the join must
get right: monthly releases after the month, GDP estimates revised twice and again each
September, seasonal revisions each January or February, a recession indicator that marks
past months only when a turning point is announced, daily market rates on business days,
and annual values that appear in a yearly database update and are revised later.
"""

import csv
import io
import math
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from multiverse_pipelines.macro.availability import next_target_day, target_holiday

FIRST_YEAR = 2008
OPEN_END = "9999-12-31"
# Synthetic turning points: (first recession month, last recession month, announced on).
RECESSIONS = (
    (date(2008, 1, 1), date(2009, 6, 1), date(2008, 12, 1)),
    (date(2020, 3, 1), date(2020, 4, 1), date(2020, 6, 8)),
)


def _months(until: date) -> list[date]:
    found, month = [], date(FIRST_YEAR - 1, 1, 1)
    while month < date(until.year, until.month, 1):
        found.append(month)
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return found


def _next_month(month: date) -> date:
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def _business_day(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _first_friday(month: date) -> date:
    return month + timedelta(days=(4 - month.weekday()) % 7)


def _row(start: date, end: date | None, period: date, value: str) -> dict[str, str]:
    return {
        "realtime_start": start.isoformat(),
        "realtime_end": end.isoformat() if end else OPEN_END,
        "date": period.isoformat(),
        "value": value,
    }


def _alfred(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "realtime_start": "1776-07-04",
        "realtime_end": OPEN_END,
        "output_type": 1,
        "file_type": "json",
        "count": len(rows),
        "observations": sorted(rows, key=lambda r: (r["date"], r["realtime_start"])),
    }


def _revised_monthly(
    until: date,
    release: Callable[[date], date],
    revision_month: int,
    level: Callable[[date, int], float],
    digits: int,
) -> dict[str, Any]:
    """A monthly series released after the month; each year the last 12 months are revised."""
    rows: list[dict[str, str]] = []
    for month in _months(until):
        first = release(month)
        if first > until:
            continue
        revisions = [
            date(year, revision_month, 15)
            for year in (month.year + 1, month.year + 2)
            if first < date(year, revision_month, 15) <= until
        ]
        starts = [first, *revisions]
        for index, start in enumerate(starts):
            end = starts[index + 1] - timedelta(days=1) if index + 1 < len(starts) else None
            rows.append(_row(start, end, month, f"{level(month, index):.{digits}f}"))
    return _alfred(rows)


def fedfunds(until: date) -> dict[str, Any]:
    rows = []
    for month in _months(until):
        released = _business_day(_next_month(month) + timedelta(days=1))
        if released <= until:
            t = (month.year - FIRST_YEAR) * 12 + month.month
            rows.append(
                _row(released, None, month, f"{max(0.05, 2.2 + 2.1 * math.sin(t / 19)):.2f}")
            )
    return _alfred(rows)


def cpi(until: date) -> dict[str, Any]:
    def level(month: date, revision: int) -> float:
        t = (month.year - FIRST_YEAR) * 12 + month.month
        return 210 * 1.0021**t * (1 + 0.0004 * math.sin(t)) + 0.03 * revision

    return _revised_monthly(until, lambda m: _next_month(m) + timedelta(days=12), 2, level, 3)


def unemployment(until: date) -> dict[str, Any]:
    def level(month: date, revision: int) -> float:
        t = (month.year - FIRST_YEAR) * 12 + month.month
        return 6.0 + 2.5 * math.cos(t / 23) + 0.1 * revision

    return _revised_monthly(until, lambda m: _first_friday(_next_month(m)), 1, level, 1)


def recession(until: date) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for month in _months(until):
        released = _business_day(_next_month(month) + timedelta(days=2))
        if released > until:
            continue
        flag = next((r for r in RECESSIONS if r[0] <= month <= r[1]), None)
        announced = flag[2] if flag else None
        if announced is None or announced <= released:
            rows.append(_row(released, None, month, "1" if flag else "0"))
            continue
        # Published as expansion; marked as recession once the turning point is announced.
        rows.append(_row(released, announced - timedelta(days=1), month, "0"))
        if announced <= until:
            rows.append(_row(announced, None, month, "1"))
    return _alfred(rows)


def gdp(until: date) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    quarter = date(FIRST_YEAR - 1, 1, 1)
    while quarter < until:
        end = date(quarter.year + (quarter.month + 2) // 12, (quarter.month + 2) % 12 + 1, 1)
        t = (quarter.year - FIRST_YEAR) * 4 + quarter.month // 3
        base = 16000 * 1.005**t * (0.97 if date(2020, 4, 1) <= quarter <= date(2020, 7, 1) else 1)
        releases = [end + timedelta(days=27), end + timedelta(days=57), end + timedelta(days=87)]
        annual = date(end.year + 1, 9, 26)
        releases.append(annual)
        starts = [r for r in releases if r <= until]
        for index, start in enumerate(starts):
            stop = starts[index + 1] - timedelta(days=1) if index + 1 < len(starts) else None
            rows.append(_row(start, stop, quarter, f"{base * (1 + 0.002 * index):.3f}"))
        quarter = end
    return _alfred(rows)


def daily(until: date, level: Callable[[int], float]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    day = date(FIRST_YEAR - 1, 12, 1)
    while day <= until:
        if day.weekday() < 5:
            released = _business_day(day + timedelta(days=1))
            if released <= until:
                t = (day - date(FIRST_YEAR, 1, 1)).days
                rows.append(_row(released, None, day, f"{level(t):.2f}"))
        day += timedelta(days=1)
    return _alfred(rows)


def ecb_csv(until: date) -> str:
    keys: dict[str, Callable[[int], float]] = {
        "EXR.D.USD.EUR.SP00.A": lambda t: 1.25 + 0.15 * math.sin(t / 400),
        "FM.D.U2.EUR.4F.KR.DFR.LEV": lambda t: max(-0.5, 1.5 * math.cos(t / 900)),
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y": lambda t: 2.0 + 1.6 * math.sin(t / 700),
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("KEY", "FREQ", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"))
    for key, level in keys.items():
        day = date(FIRST_YEAR - 1, 12, 1)
        while day <= until:
            published = next_target_day(day) if key.startswith("YC") else day
            if day.weekday() < 5 and not target_holiday(day) and published <= until:
                t = (day - date(FIRST_YEAR, 1, 1)).days
                writer.writerow((key, key.split(".")[1], day.isoformat(), f"{level(t):.4f}", "A"))
            day += timedelta(days=1)
    return buffer.getvalue()


def worldbank_snapshots(until: date, code: str) -> list[list[Any]]:
    """One database update each July: years up to the year before, the last two revised."""
    snapshots: list[list[Any]] = []
    for year in range(FIRST_YEAR + 1, until.year + 1):
        updated = date(year, 7, 1)
        if updated > until:
            break
        rows = []
        for iso, name, shift in (("USA", "United States", 0.0), ("EMU", "Euro area", -0.6)):
            for observed in range(FIRST_YEAR - 1, year):
                revision = 0.1 * (year - observed - 1) if year - observed <= 3 else 0.2
                value = _wb_value(code, observed, shift) + revision
                rows.append(
                    {
                        "indicator": {"id": code, "value": code},
                        "country": {"id": iso[:2], "value": name},
                        "countryiso3code": iso,
                        "date": str(observed),
                        "value": round(value, 3),
                        "unit": "",
                        "obs_status": "",
                        "decimal": 1,
                    }
                )
        header = {
            "page": 1,
            "pages": 1,
            "per_page": 20000,
            "total": len(rows),
            "sourceid": "2",
            "lastupdated": updated.isoformat(),
        }
        snapshots.append([header, rows])
    return snapshots


def _wb_value(code: str, year: int, shift: float) -> float:
    t = year - FIRST_YEAR
    if code == "NY.GDP.PCAP.KD":
        return 55000 * 1.012**t * (1 + shift / 10)
    if code == "SL.UEM.TOTL.ZS":
        return 6.5 + 2 * math.cos(t / 3) - shift
    if code == "FP.CPI.TOTL.ZG":
        return 2.1 + 1.2 * math.cos(t / 2.5) + shift / 2
    return 2.0 + 1.5 * math.sin(t / 2) + shift


def fred_documents(until: date) -> dict[str, dict[str, Any]]:
    return {
        "FEDFUNDS": fedfunds(until),
        "CPIAUCSL": cpi(until),
        "UNRATE": unemployment(until),
        "GDPC1": gdp(until),
        "DGS10": daily(until, lambda t: 2.8 + 1.4 * math.sin(t / 500)),
        "T10Y2Y": daily(until, lambda t: 1.0 + 1.3 * math.cos(t / 600)),
        "USREC": recession(until),
    }


WB_CODES = ("NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS", "NY.GDP.PCAP.KD")
