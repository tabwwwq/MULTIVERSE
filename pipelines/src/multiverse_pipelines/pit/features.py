"""Features from an as-of panel, and nothing else.

Every function here takes panel cells only, never the warehouse, a file or the clock, so
a feature cannot see more than its panel: if the panel holds only what was public at the
cutoff, so do the features (ADR-0019). The mask propagates: a feature is masked unless
every cell it needs is, and an empty input never becomes zero.

- ``ttm_<flow>``: the last four quarters added up (trailing twelve months);
- ``yoy_<flow>``: the quarter against the same quarter a year before, as a fraction.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from multiverse_contracts.normalized import PeriodKind
from multiverse_contracts.pit import PanelCell
from multiverse_pipelines.xbrl.concepts import CALCULATED, METRICS

FLOWS = tuple(
    spec.metric for spec in METRICS if spec.kind is PeriodKind.DURATION and spec.additive
) + tuple(spec.metric for spec in CALCULATED)
GROWTH = ("revenue", "operating_income", "cfo")
FRACTION = Decimal("0.000001")


@dataclass(frozen=True)
class Feature:
    cik: str
    calendar_quarter: str
    lag: int
    name: str
    value: Decimal | None
    mask: bool
    reason: str | None = None


def _series(cells: Sequence[PanelCell]) -> dict[tuple[str, str], list[PanelCell]]:
    """Per company and metric, cells from the newest quarter (lag 0) back."""
    found: dict[tuple[str, str], list[PanelCell]] = defaultdict(list)
    for cell in sorted(cells, key=lambda c: (c.cik, c.metric, c.lag)):
        found[(cell.cik, cell.metric)].append(cell)
    return found


def trailing_twelve_months(cells: Sequence[PanelCell], metric: str) -> list[Feature]:
    features: list[Feature] = []
    for (cik, name), series in sorted(_series(cells).items()):
        if name != metric:
            continue
        for position, cell in enumerate(series):
            window = series[position : position + 4]
            missing = [c.calendar_quarter for c in window if not c.mask]
            if len(window) < 4 or missing:
                reason = (
                    "fewer than four quarters in the panel"
                    if len(window) < 4
                    else f"needs four masked quarters; missing {', '.join(missing)}"
                )
                features.append(
                    Feature(
                        cik, cell.calendar_quarter, cell.lag, f"ttm_{metric}", None, False, reason
                    )
                )
                continue
            total = sum((Decimal(c.value or "0") for c in window), Decimal(0))
            features.append(
                Feature(cik, cell.calendar_quarter, cell.lag, f"ttm_{metric}", total, True)
            )
    return features


def year_over_year(cells: Sequence[PanelCell], metric: str) -> list[Feature]:
    features: list[Feature] = []
    for (cik, name), series in sorted(_series(cells).items()):
        if name != metric:
            continue
        for position, cell in enumerate(series):
            name_ = f"yoy_{metric}"
            if position + 4 >= len(series):
                features.append(
                    Feature(
                        cik,
                        cell.calendar_quarter,
                        cell.lag,
                        name_,
                        None,
                        False,
                        "the same quarter a year before is not in the panel",
                    )
                )
                continue
            before = series[position + 4]
            if not (cell.mask and before.mask):
                features.append(
                    Feature(
                        cik,
                        cell.calendar_quarter,
                        cell.lag,
                        name_,
                        None,
                        False,
                        "needs both quarters masked",
                    )
                )
                continue
            base = Decimal(before.value or "0")
            if base <= 0:
                features.append(
                    Feature(
                        cik,
                        cell.calendar_quarter,
                        cell.lag,
                        name_,
                        None,
                        False,
                        "growth is undefined from a zero or negative base",
                    )
                )
                continue
            growth = (Decimal(cell.value or "0") / base - 1).quantize(FRACTION)
            features.append(Feature(cik, cell.calendar_quarter, cell.lag, name_, growth, True))
    return features


def build_features(cells: Sequence[PanelCell]) -> list[Feature]:
    features: list[Feature] = []
    for metric in FLOWS:
        features += trailing_twelve_months(cells, metric)
    for metric in GROWTH:
        features += year_over_year(cells, metric)
    return sorted(features, key=lambda f: (f.cik, f.name, f.lag))
