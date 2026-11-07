"""U.S. Treasury par yields: the rates of the model, straight from their publisher (Stage 24b).

The terms of FRED forbid machine learning on its content, so rates no longer come through it. The
Treasury publishes one CSV per year. A yield of a day is known at the close of that day and is not
revised, so a value is available at an origin when its date is not later than the origin.

    python -m multiverse_pipelines.macro.treasury

Files stay in ``<raw dir>/treasury``. The current year changes daily; earlier years do not.
"""

import csv
import io
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from multiverse_config import Settings, load_settings

URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
HOST = "home.treasury.gov"
FIRST_YEAR = 2009
SHORT = "3 Mo"
LONG = "10 Yr"


@dataclass(frozen=True)
class Yields:
    day: date
    short: float | None
    long: float | None


def _number(text: str | None) -> float | None:
    return float(text) if text not in (None, "", "N/A") else None


def parse(text: str) -> list[Yields]:
    rows = csv.DictReader(io.StringIO(text))
    found = [
        Yields(
            day=datetime.strptime(row["Date"], "%m/%d/%Y").replace(tzinfo=UTC).date(),
            short=_number(row.get(SHORT)),
            long=_number(row.get(LONG)),
        )
        for row in rows
    ]
    return sorted(found, key=lambda item: item.day)


def load(folder: Path) -> list[Yields]:
    found: list[Yields] = []
    for path in sorted(folder.glob("yields-*.csv")):
        found += parse(path.read_text(encoding="utf-8"))
    return sorted(found, key=lambda item: item.day)


def as_of(rows: Sequence[Yields], day: date) -> Yields | None:
    """The last published day not after ``day``: what a reader could know that evening."""
    index = bisect_right([row.day for row in rows], day)
    return rows[index - 1] if index else None


def fetch(settings: Settings, today: date, transport: httpx.BaseTransport | None = None) -> int:
    if not settings.allow_network_downloads:
        raise ValueError("downloads are off: MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true for one run")
    folder = settings.raw_dir / "treasury"
    folder.mkdir(parents=True, exist_ok=True)
    fetched = 0
    with httpx.Client(timeout=60, transport=transport, follow_redirects=False) as client:
        for year in range(FIRST_YEAR, today.year + 1):
            path = folder / f"yields-{year}.csv"
            if path.exists() and year < today.year:
                continue
            url = URL.format(year=year)
            if urlsplit(url).hostname != HOST:
                raise ValueError(f"{url} is not on {HOST}")
            answer = client.get(url, headers={"User-Agent": "multiverse-research"})
            answer.raise_for_status()
            if not parse(answer.text):
                raise ValueError(f"{url} held no rows")
            path.write_text(answer.text, encoding="utf-8", newline="\n")
            fetched += 1
    return fetched


def main() -> int:
    settings = load_settings()
    count = fetch(settings, datetime.now(UTC).date())
    rows = load(settings.raw_dir / "treasury")
    print(f"{count} files fetched, {len(rows)} days, last {rows[-1].day}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
