"""Series coverage and timestamp QA of the macro store.

Per registered series: periods, vintages, first and last period, how availability is
known, the publication lag (first availability minus period end, in days), how many
periods were revised, and problems:

- ``published_before_period_end``: a monthly, quarterly or annual value available before
  its period ended (impossible for a measurement; a forecast would be one);
- ``missing_value``: the source marks a period missing;
- ``gap``: a monthly or quarterly period missing between published ones.
"""

import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from multiverse_contracts.macro import Frequency, MacroSeries
from multiverse_pipelines.macro.store import MacroStore
from multiverse_pipelines.pit.clock import eastern_date


@dataclass
class SeriesQA:
    series: MacroSeries
    periods: int = 0
    intervals: int = 0
    vintages: int = 0
    first_period: date | None = None
    last_period: date | None = None
    basis: Counter[str] = field(default_factory=Counter)
    lag_days: list[int] = field(default_factory=list)
    revised_periods: int = 0
    problems: Counter[str] = field(default_factory=Counter)

    def lag(self) -> str:
        if not self.lag_days:
            return "n/a"
        return f"{min(self.lag_days)} / {statistics.median(self.lag_days):g} / {max(self.lag_days)}"


def _step(period: date, frequency: Frequency) -> date:
    months = 1 if frequency is Frequency.MONTHLY else 3
    index = period.year * 12 + period.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def series_qa(store: MacroStore, series: Sequence[MacroSeries]) -> list[SeriesQA]:
    report: list[SeriesQA] = []
    for item in series:
        qa = SeriesQA(item)
        history = store.history(item.series_id)
        report.append(qa)
        if not history:
            continue
        by_period: dict[date, list[Any]] = defaultdict(list)
        for observation in history:
            by_period[observation.period_start].append(observation)
            qa.basis[observation.basis.value] += 1
            if observation.value is None:
                qa.problems["missing_value"] += 1
        qa.intervals = len(history)
        qa.periods = len(by_period)
        qa.vintages = len({o.available_from for o in history})
        qa.first_period, qa.last_period = min(by_period), max(by_period)
        for items in by_period.values():
            first = min(items, key=lambda o: o.available_from)
            lag = (eastern_date(first.available_from) - first.period_end).days
            qa.lag_days.append(lag)
            if item.frequency is not Frequency.DAILY and lag < 0:
                qa.problems["published_before_period_end"] += 1
            if len({o.value for o in items}) > 1:
                qa.revised_periods += 1
        if item.frequency in (Frequency.MONTHLY, Frequency.QUARTERLY):
            period = qa.first_period
            while period < qa.last_period:
                period = _step(period, item.frequency)
                if period not in by_period:
                    qa.problems["gap"] += 1
    return report


def to_markdown(report: Sequence[SeriesQA], *, synthetic: bool, unavailable: dict[str, str]) -> str:
    title = "Macro series coverage and timestamp QA" + (" (SYNTHETIC data)" if synthetic else "")
    lines = [
        f"# {title}",
        "",
        "Publication lag: days from period end to first availability (min / median / max).",
        "",
        "| series | feature | frequency | vintages | periods | first to last | availability "
        "| lag days | revised periods | problems |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for qa in report:
        s = qa.series
        if qa.periods == 0:
            reason = unavailable.get(s.source_id, "not in the store")
            lines.append(
                f"| {s.series_id} | {s.feature} | {s.frequency.value} | - | - | {reason} "
                "| - | - | - | - |"
            )
            continue
        basis = ", ".join(f"{k} {v}" for k, v in sorted(qa.basis.items()))
        problems = ", ".join(f"{k} {v}" for k, v in sorted(qa.problems.items())) or "none"
        lines.append(
            f"| {s.series_id} | {s.feature} | {s.frequency.value} | {qa.vintages} | {qa.periods} | "
            f"{qa.first_period} to {qa.last_period} | {basis} | {qa.lag()} | "
            f"{qa.revised_periods} | {problems} |"
        )
    lines += ["", "## Series metadata", ""]
    for qa in report:
        s = qa.series
        lines += [
            f"### {s.series_id} — {s.title}",
            "",
            f"- Geography {s.geography}; {s.frequency.value}; unit: {s.unit}; seasonal adjustment: "
            f"{s.seasonal_adjustment.value}; period label: {s.period_label}.",
            f"- Released in {s.release_timezone}; lag: {s.publication_lag}; "
            f"revisions: {s.revision_cadence}.",
            f"- Business days: {s.business_days}; vintages kept: {s.vintage_support.value}.",
            f"- Feature `{s.feature}` = {s.transform.value}. {s.attribution}",
            "",
        ]
    return "\n".join(lines)


def to_json(report: Sequence[SeriesQA]) -> list[dict[str, Any]]:
    return [
        {
            "series_id": qa.series.series_id,
            "feature": qa.series.feature,
            "periods": qa.periods,
            "intervals": qa.intervals,
            "vintages": qa.vintages,
            "first_period": qa.first_period.isoformat() if qa.first_period else None,
            "last_period": qa.last_period.isoformat() if qa.last_period else None,
            "basis": dict(qa.basis),
            "lag_days": qa.lag(),
            "revised_periods": qa.revised_periods,
            "problems": dict(qa.problems),
        }
        for qa in report
    ]


def write_qa(
    report: Sequence[SeriesQA], folder: Path, *, synthetic: bool, unavailable: dict[str, str]
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "series.json").write_text(
        json.dumps([qa.series.model_dump(mode="json") for qa in report], indent=2) + "\n",
        encoding="utf-8",
    )
    (folder / "qa.json").write_text(json.dumps(to_json(report), indent=2) + "\n", encoding="utf-8")
    (folder / "qa.md").write_text(
        to_markdown(report, synthetic=synthetic, unavailable=unavailable), encoding="utf-8"
    )
    return folder
