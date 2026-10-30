"""Source documents into observations with their availability.

- ALFRED ``series/observations`` with the full real-time range: one row per value and
  real-time period (``realtime_start`` … ``realtime_end``, both days included).
- ECB ``csvdata``: current values by series key and ``TIME_PERIOD``.
- World Bank v2 JSON: a header with ``lastupdated`` and the rows; several dated
  snapshots of one indicator become intervals of availability.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from multiverse_contracts.macro import (
    AvailabilityBasis,
    Frequency,
    MacroObservation,
    VintageSupport,
)
from multiverse_pipelines.macro import availability
from multiverse_pipelines.macro.registry import BY_ID
from multiverse_pipelines.xbrl.normalize import decimal_text

OPEN_END = "9999-12-31"
ECB_RULES = {
    "EXR": availability.ecb_reference_rate,
    "YC": availability.ecb_yield_curve,
    "FM": availability.ecb_key_rate,
}


class UnknownSeriesError(ValueError):
    """A document holds a series that is not registered."""


def period_end(start: date, frequency: Frequency) -> date:
    if frequency is Frequency.DAILY:
        return start
    if frequency is Frequency.ANNUAL:
        return date(start.year, 12, 31)
    months = 1 if frequency is Frequency.MONTHLY else 3
    month = start.month - 1 + months
    following = date(start.year + month // 12, month % 12 + 1, 1)
    return following - timedelta(days=1)


def _number(text: object) -> str | None:
    if text is None or text in (".", "", "NaN"):
        return None
    try:
        return decimal_text(Decimal(str(text)))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {text!r}") from exc


def _series(series_id: str) -> Frequency:
    series = BY_ID.get(series_id)
    if series is None:
        raise UnknownSeriesError(f"{series_id} is not in the macro registry")
    return series.frequency


def alfred_observations(
    code: str, doc: Mapping[str, Any], *, raw_sha256: str | None = None, synthetic: bool = False
) -> list[MacroObservation]:
    series_id = f"fred:{code}"
    frequency = _series(series_id)
    found: list[MacroObservation] = []
    for row in doc["observations"]:
        start = date.fromisoformat(row["date"])
        vintage = date.fromisoformat(row["realtime_start"])
        end = row["realtime_end"]
        available_to = (
            None
            if end == OPEN_END
            else availability.vintage_available(date.fromisoformat(end) + timedelta(days=1))
        )
        found.append(
            MacroObservation(
                series_id=series_id,
                period_start=start,
                period_end=period_end(start, frequency),
                value=_number(row["value"]),
                available_from=availability.vintage_available(vintage),
                available_to=available_to,
                basis=AvailabilityBasis.VINTAGE,
                source_vintage=vintage,
                raw_sha256=raw_sha256,
                synthetic=synthetic,
            )
        )
    return found


def fred_current_observations(
    code: str, doc: Mapping[str, Any], *, raw_sha256: str | None = None, synthetic: bool = False
) -> list[MacroObservation]:
    """Current values of an unrevised daily FRED series, available by the H.15 rule."""
    series_id = f"fred:{code}"
    frequency = _series(series_id)
    found: list[MacroObservation] = []
    for row in doc["observations"]:
        value = _number(row["value"])
        if value is None:
            continue
        start = date.fromisoformat(row["date"])
        found.append(
            MacroObservation(
                series_id=series_id,
                period_start=start,
                period_end=period_end(start, frequency),
                value=value,
                available_from=availability.h15_daily(start),
                basis=AvailabilityBasis.SCHEDULE,
                raw_sha256=raw_sha256,
                synthetic=synthetic,
            )
        )
    return found


def fred_observations(
    code: str, doc: Mapping[str, Any], *, raw_sha256: str | None = None, synthetic: bool = False
) -> list[MacroObservation]:
    """ALFRED vintages, or current values for a series registered without vintages."""
    if BY_ID[f"fred:{code}"].vintage_support is VintageSupport.NONE:
        return fred_current_observations(code, doc, raw_sha256=raw_sha256, synthetic=synthetic)
    return alfred_observations(code, doc, raw_sha256=raw_sha256, synthetic=synthetic)


def ecb_observations(
    text: str, *, raw_sha256: str | None = None, synthetic: bool = False
) -> list[MacroObservation]:
    found: list[MacroObservation] = []
    for row in csv.DictReader(io.StringIO(text)):
        key = row["KEY"]
        series_id = f"ecb:{key}"
        _series(series_id)
        day = date.fromisoformat(row["TIME_PERIOD"])
        rule = ECB_RULES[key.split(".")[0]]
        value = _number(row["OBS_VALUE"])
        if value is None:
            continue
        found.append(
            MacroObservation(
                series_id=series_id,
                period_start=day,
                period_end=day,
                value=value,
                available_from=rule(day),
                basis=AvailabilityBasis.SCHEDULE,
                raw_sha256=raw_sha256,
                synthetic=synthetic,
            )
        )
    return found


@dataclass(frozen=True)
class Snapshot:
    """One World Bank response: when the database was updated, and its rows."""

    updated: date
    rows: Sequence[Mapping[str, Any]]
    raw_sha256: str | None = None


def worldbank_snapshot(doc: Sequence[Any], *, raw_sha256: str | None = None) -> Snapshot:
    header, rows = doc[0], doc[1] or []
    return Snapshot(date.fromisoformat(header["lastupdated"]), rows, raw_sha256)


def worldbank_observations(
    snapshots: Iterable[Snapshot], *, synthetic: bool = False
) -> list[MacroObservation]:
    """Values over the snapshots that contained them: a change opens a new interval."""
    history: dict[tuple[str, int], list[tuple[Snapshot, str | None]]] = defaultdict(list)
    ordered = sorted(snapshots, key=lambda s: s.updated)
    for snapshot in ordered:
        seen: set[tuple[str, int]] = set()
        indicators: set[str] = set()
        for row in snapshot.rows:
            series_id = f"wb:{row['countryiso3code']}.{row['indicator']['id']}"
            _series(series_id)
            indicators.add(row["indicator"]["id"])
            key = (series_id, int(row["date"]))
            seen.add(key)
            history[key].append((snapshot, _number(row["value"])))
        # A value disappears only from a snapshot of its own indicator.
        for key, items in history.items():
            own = key[0].split(".", 1)[1] in indicators
            if own and key not in seen and items and items[-1][0] is not snapshot:
                items.append((snapshot, None))
    found: list[MacroObservation] = []
    for (series_id, year), items in sorted(history.items()):
        current: tuple[Snapshot, str | None] | None = None
        for snapshot, value in items:
            if current is not None and current[1] == value:
                continue
            if current is not None and current[1] is not None:
                found.append(_wb(series_id, year, current, snapshot, synthetic))
            current = (snapshot, value)
        if current is not None and current[1] is not None:
            found.append(_wb(series_id, year, current, None, synthetic))
    return found


def _wb(
    series_id: str,
    year: int,
    current: tuple[Snapshot, str | None],
    replaced_by: Snapshot | None,
    synthetic: bool,
) -> MacroObservation:
    snapshot, value = current
    return MacroObservation(
        series_id=series_id,
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        value=value,
        available_from=availability.snapshot_available(snapshot.updated),
        available_to=availability.snapshot_available(replaced_by.updated) if replaced_by else None,
        basis=AvailabilityBasis.SNAPSHOT,
        source_vintage=snapshot.updated,
        raw_sha256=snapshot.raw_sha256,
        synthetic=synthetic,
    )
