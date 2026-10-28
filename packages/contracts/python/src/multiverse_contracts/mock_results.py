"""Mock scenario results for the interface (Stage 06). Not a model, not a forecast.

The history comes from the synthetic demo dossiers, filtered to what was public at the
cutoff. Each path then continues with a random walk: quarterly revenue growth and the
EBITDA margin follow the company's own recent history. Alternates reuse the baseline's
shocks path by path (paired paths, PRD FR-SI-07) and add mechanical decision effects
whose uncertain inputs are drawn from the decision's own distributions. Everything is
labelled mock and demo; the Monte Carlo engine of Stage 22 replaces it.

Usage:
    uv run python -m multiverse_contracts.mock_results           # write fixtures/mock/results.json
    uv run python -m multiverse_contracts.mock_results --check   # exit 1 if the file is stale
"""

import argparse
import json
import math
import random
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from multiverse_contracts.companies import CompanyDossier
from multiverse_contracts.decisions import (
    CapexExpansion,
    RndChange,
    ScenarioDraft,
    WorkforceRestructure,
    add_quarters,
)
from multiverse_contracts.demo import build_dossier, demo_specs
from multiverse_contracts.distributions import FixedValue, TriangularRange, UniformRange
from multiverse_contracts.results import ScenarioResult
from multiverse_contracts.version import CONTRACTS_VERSION

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "mock" / "results.json"
GENERATED_AT = "2026-10-28T00:00:00Z"
MODEL = "mock-paired-walk 0.1 (interface mock, no model)"
PATHS = 500
HORIZON = 12
EV_MULTIPLE = 10
QUANTILES = (0.1, 0.5, 0.9)

NORTHWIND = "5b1f3c2e-8a4d-4e7b-9c61-2f0d7a9e4b13"
HALCYON = "a7c2e9d4-1f3b-4c8a-b5e6-0d9f2a7c3e18"

DEFINITIONS = {
    "revenue": ("Revenue", "Revenue per quarter."),
    "ebitda": ("EBITDA (calculated)", "Operating income plus depreciation and amortization."),
    "fcf": ("FCF (CFO − CAPEX)", "Operating cash flow minus capital expenditure per quarter."),
    "net_debt": ("Net debt", "Debt minus cash at quarter end. Negative means net cash."),
    "ev": (
        "EV (mock: 10 × trailing EBITDA)",
        "Illustrative enterprise value: ten times trailing-twelve-month EBITDA. Not a valuation.",
    ),
}

STEP_EXPLANATIONS = {
    "Extra R&D expense": "Incremental R&D in the quarter, minus the capitalized share.",
    "Revenue from R&D at the base margin": (
        "Mock revenue return on cumulative extra R&D after the adoption delay, at the "
        "path's EBITDA margin."
    ),
    "Investment": "Capital expenditure paid during construction.",
    "EBITDA from new capacity": "Revenue from used and sold new capacity at the path's margin.",
    "Payroll savings realized": "Realized share of the gross payroll change.",
    "One-off restructuring cost": "Severance in months of salary, charged when the effect starts.",
    "Lost output during the transition": "Revenue lost to lower productivity during the ramp.",
}


@dataclass(frozen=True)
class History:
    """What was public at the cutoff, oldest first."""

    ends: tuple[date, ...]
    labels: tuple[str, ...]
    values: dict[str, tuple[float, ...]]
    filed: dict[str, tuple[date, ...]]
    sources: dict[str, tuple[str, ...]]
    rnd_ttm: float | None


@dataclass
class SimPath:
    revenue: list[float]
    ebitda: list[float]
    fcf: list[float]
    net_debt: list[float]


@dataclass(frozen=True)
class Timing:
    """Decision timing in forecast-quarter indexes (0 = first forecast quarter)."""

    effective: int
    start: int
    ramp: int

    def factor(self, t: int) -> float:
        if t < self.start:
            return 0.0
        return min(1.0, (t - self.start + 1) / (self.ramp + 1))


# An effect returns per-quarter changes of revenue, EBITDA and FCF, plus "step:" series
# that add up to the EBITDA or FCF change and feed the waterfall.
Effect = Callable[[SimPath, random.Random, Timing], dict[str, list[float]]]


def _history(dossier: CompanyDossier, as_of: date, quarters: int = 12) -> History:
    filed = {filing.filing_id: filing.filed_at.date() for filing in dossier.filings}
    rows: dict[str, dict[date, tuple[float, date, str, str]]] = {}
    for value in dossier.values:
        # Flows are fiscal quarters; net debt is an instant value at the same quarter end.
        if value.period.type not in ("fiscal_quarter", "instant") or value.quantity is None:
            continue
        source = value.source_ids[0]
        if filed[source] > as_of:
            continue
        label = f"FY{value.period.fiscal_year} Q{value.period.fiscal_quarter}"
        rows.setdefault(value.metric, {})[value.period.end_date] = (
            float(value.quantity.value),
            filed[source],
            source,
            label,
        )
    ends = sorted(rows["revenue"])[-quarters:]
    names = {
        "revenue": "revenue",
        "ebitda_calculated": "ebitda",
        "fcf_simple": "fcf",
        "net_debt": "net_debt",
    }
    values, filed_on, sources = {}, {}, {}
    for metric, name in names.items():
        picked = [rows[metric][end] for end in ends]
        values[name] = tuple(row[0] for row in picked)
        filed_on[name] = tuple(row[1] for row in picked)
        sources[name] = tuple(row[2] for row in picked)
    rnd = rows.get("rnd_expense", {})
    window = ends[-4:]
    rnd_ttm = sum(rnd[end][0] for end in window) if all(end in rnd for end in window) else None
    labels = tuple(rows["revenue"][end][3] for end in ends)
    return History(tuple(ends), labels, values, filed_on, sources, rnd_ttm)


def _next_label(label: str) -> str:
    year, quarter = int(label[2:6]), int(label[-1])
    year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return f"FY{year} Q{quarter}"


def _forecast_calendar(history: History) -> tuple[list[date], list[str]]:
    ends, labels = [], []
    end, label = history.ends[-1], history.labels[-1]
    for _ in range(HORIZON):
        end, label = add_quarters(end, 1), _next_label(label)
        ends.append(end)
        labels.append(label)
    return ends, labels


def _baseline(history: History, rng: random.Random) -> SimPath:
    revenue = history.values["revenue"]
    growth = [math.log(b / a) for a, b in pairwise(revenue)]
    mu = min(0.06, max(-0.04, sum(growth) / len(growth)))
    sigma = max(0.02, math.sqrt(sum((g - mu) ** 2 for g in growth) / len(growth)))
    margins = [e / r for e, r in zip(history.values["ebitda"], revenue, strict=True)][-8:]
    margin_mean = sum(margins) / len(margins)
    ebitda_history = history.values["ebitda"]
    conversions = [f / e for f, e in zip(history.values["fcf"], ebitda_history, strict=True)]
    conversion = min(0.9, max(0.2, sum(conversions[-8:]) / len(conversions[-8:])))

    path = SimPath([], [], [], [])
    rev, margin, debt = revenue[-1], margins[-1], history.values["net_debt"][-1]
    for _ in range(HORIZON):
        rev *= math.exp(mu + sigma * rng.gauss(0, 1))
        margin = margin_mean + 0.5 * (margin - margin_mean) + 0.01 * rng.gauss(0, 1)
        ebitda = rev * margin
        fcf = ebitda * conversion
        debt -= fcf
        path.revenue.append(rev)
        path.ebitda.append(ebitda)
        path.fcf.append(fcf)
        path.net_debt.append(debt)
    return path


def _draw(distribution: FixedValue | UniformRange | TriangularRange, rng: random.Random) -> float:
    if isinstance(distribution, FixedValue):
        return float(distribution.value)
    if isinstance(distribution, UniformRange):
        return rng.uniform(float(distribution.low), float(distribution.high))
    low, high = float(distribution.low), float(distribution.high)
    return rng.triangular(low, high, float(distribution.mode))


def apply_effect(base: SimPath, effect: dict[str, list[float]]) -> SimPath:
    """Alternate path: the baseline plus the decision's changes; net debt follows cash."""
    revenue = [b + d for b, d in zip(base.revenue, effect["revenue"], strict=True)]
    ebitda = [b + d for b, d in zip(base.ebitda, effect["ebitda"], strict=True)]
    fcf = [b + d for b, d in zip(base.fcf, effect["fcf"], strict=True)]
    debt = base.net_debt[0] + base.fcf[0]  # net debt before the first forecast quarter
    net_debt = []
    for flow in fcf:
        debt -= flow
        net_debt.append(debt)
    return SimPath(revenue, ebitda, fcf, net_debt)


def rnd_effect(decision: RndChange, rnd_ttm: float) -> Effect:
    share = float(decision.magnitude.value)
    capitalized = float(decision.capitalized_fraction)
    per_point = decision.magnitude.unit == "pp_of_revenue"

    def effect(base: SimPath, rng: random.Random, timing: Timing) -> dict[str, list[float]]:
        delay = round(_draw(decision.adoption_delay_quarters, rng))
        # Mock prior: quarterly revenue per dollar of cumulative extra R&D. Not an estimate.
        return_rate = rng.triangular(0.02, 0.2, 0.08)
        extra: list[float] = []
        out: dict[str, list[float]] = {
            "revenue": [],
            "ebitda": [],
            "fcf": [],
            "step:Extra R&D expense": [],
            "step:Revenue from R&D at the base margin": [],
        }
        for t in range(HORIZON):
            base_amount = share / 100 * base.revenue[t] if per_point else share * rnd_ttm / 4
            amount = base_amount * timing.factor(t)
            extra.append(amount)
            uplift = return_rate * sum(extra[: max(0, t - delay + 1)])
            gain = uplift * base.ebitda[t] / base.revenue[t]
            out["revenue"].append(uplift)
            out["ebitda"].append(gain - amount * (1 - capitalized))
            out["fcf"].append(gain - amount)
            out["step:Extra R&D expense"].append(-amount * (1 - capitalized))
            out["step:Revenue from R&D at the base margin"].append(gain)
        return out

    return effect


def capex_effect(decision: CapexExpansion) -> Effect:
    amount = float(decision.magnitude.value)
    capacity = float(decision.capacity_increase)
    sold_share = 0.6  # mock: share of the used new capacity that finds buyers

    def effect(base: SimPath, rng: random.Random, timing: Timing) -> dict[str, list[float]]:
        utilization = _draw(decision.utilization, rng)
        build = max(1, timing.start - timing.effective)
        out: dict[str, list[float]] = {
            "revenue": [],
            "ebitda": [],
            "fcf": [],
            "step:Investment": [],
            "step:EBITDA from new capacity": [],
        }
        for t in range(HORIZON):
            building = timing.effective <= t < timing.effective + build
            investing = amount / build if building else 0.0
            uplift = base.revenue[t] * capacity * utilization * sold_share * timing.factor(t)
            gain = uplift * base.ebitda[t] / base.revenue[t]
            out["revenue"].append(uplift)
            out["ebitda"].append(gain)
            out["fcf"].append(gain - investing)
            out["step:Investment"].append(-investing)
            out["step:EBITDA from new capacity"].append(gain)
        return out

    return effect


def workforce_effect(decision: WorkforceRestructure) -> Effect:
    change = float(decision.magnitude.value)
    payroll_share = float(decision.payroll_to_revenue)

    def effect(base: SimPath, rng: random.Random, timing: Timing) -> dict[str, list[float]]:
        realized = _draw(decision.savings_realization, rng)
        months = _draw(decision.one_off_cost_months, rng)
        loss = _draw(decision.productivity_loss, rng)
        out: dict[str, list[float]] = {
            "revenue": [],
            "ebitda": [],
            "fcf": [],
            "step:Payroll savings realized": [],
            "step:One-off restructuring cost": [],
            "step:Lost output during the transition": [],
        }
        for t in range(HORIZON):
            factor = timing.factor(t)
            payroll = payroll_share * base.revenue[t]
            saving = -change * payroll * realized * factor
            # Payroll is quarterly; severance is months of yearly salary.
            one_off = abs(change) * payroll * 4 * months / 12 if t == timing.start else 0.0
            lost_revenue = base.revenue[t] * loss if 0 < factor < 1 else 0.0
            lost = lost_revenue * base.ebitda[t] / base.revenue[t]
            out["revenue"].append(-lost_revenue)
            out["ebitda"].append(saving - one_off - lost)
            out["fcf"].append(saving - one_off - lost)
            out["step:Payroll savings realized"].append(saving)
            out["step:One-off restructuring cost"].append(-one_off)
            out["step:Lost output during the transition"].append(-lost)
        return out

    return effect


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _usd(value: float) -> str:
    return str(round(value))


def _fraction(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _points(
    samples: list[list[float]], ends: list[date], labels: list[str], fmt: Callable[[float], str]
) -> list[dict[str, str]]:
    points = []
    for t, (end, label) in enumerate(zip(ends, labels, strict=True)):
        column = [path[t] for path in samples]
        p10, p50, p90 = (fmt(_quantile(column, q)) for q in QUANTILES)
        point = {"period_end": end.isoformat(), "fiscal_label": label}
        points.append({**point, "p10": p10, "p50": p50, "p90": p90})
    return points


def _series(path: SimPath, history: History, metric: str) -> list[float]:
    if metric != "ev":
        values: list[float] = getattr(path, metric)
        return list(values)
    combined = list(history.values["ebitda"][-3:]) + path.ebitda
    return [EV_MULTIPLE * sum(combined[t : t + 4]) for t in range(HORIZON)]


def _histogram(values: list[float], bins: int = 16) -> list[dict[str, Any]]:
    low, high = min(values), max(values)
    raw = max((high - low) / bins, 1.0)
    magnitude = 10 ** math.floor(math.log10(raw))
    width = next(step * magnitude for step in (1, 2, 2.5, 5, 10) if step * magnitude >= raw)
    start = math.floor(low / width) * width
    count = max(1, math.ceil((high - start) / width + 1e-9))
    counts = [0] * count
    for value in values:
        counts[min(int((value - start) // width), count - 1)] += 1
    return [
        {"low": _usd(start + i * width), "high": _usd(start + (i + 1) * width), "count": n}
        for i, n in enumerate(counts)
    ]


def _timing(draft: ScenarioDraft, ends: list[date]) -> Timing:
    timing = draft.decision.timing
    effective = next(i for i, end in enumerate(ends) if end >= timing.effective_date)
    return Timing(effective, effective + timing.lag_quarters, timing.ramp_quarters)


@dataclass(frozen=True)
class Alternate:
    key: str
    label: str
    draft: ScenarioDraft
    effect: Effect
    waterfall_metric: str
    waterfall_aggregation: str


def _observed(history: History, metric: str) -> list[dict[str, str]]:
    source = "ebitda" if metric == "ev" else metric
    rows = []
    for i, end in enumerate(history.ends):
        if metric == "ev":
            if i < 3:
                continue
            value = EV_MULTIPLE * sum(history.values["ebitda"][i - 3 : i + 1])
        else:
            value = history.values[metric][i]
        rows.append(
            {
                "period_end": end.isoformat(),
                "fiscal_label": history.labels[i],
                "value": _usd(value),
                "filed_at": history.filed[source][i].isoformat(),
                "source_id": history.sources[source][i],
            }
        )
    return rows


def _simulate(
    history: History, seed: int, alternates: Sequence[Alternate], timings: dict[str, Timing]
) -> tuple[list[SimPath], dict[str, list[SimPath]], dict[str, dict[str, list[float]]]]:
    baselines: list[SimPath] = []
    paths: dict[str, list[SimPath]] = {alt.key: [] for alt in alternates}
    steps: dict[str, dict[str, list[float]]] = {alt.key: {} for alt in alternates}
    for index in range(PATHS):
        base = _baseline(history, random.Random(seed * 100_003 + index))
        baselines.append(base)
        for alt in alternates:
            # Market shocks are shared with the baseline; decision inputs have their own stream.
            effect = alt.effect(base, random.Random(f"{seed}:{alt.key}:{index}"), timings[alt.key])
            paths[alt.key].append(apply_effect(base, effect))
            for name, values in effect.items():
                if name.startswith("step:"):
                    total = sum(values) if alt.waterfall_aggregation == "cumulative" else values[-1]
                    steps[alt.key].setdefault(name[5:], []).append(total)
    return baselines, paths, steps


def _metric(
    metric: str,
    history: History,
    calendar: tuple[list[date], list[str]],
    baselines: list[SimPath],
    paths: dict[str, list[SimPath]],
) -> dict[str, Any]:
    ends, labels = calendar
    base = [_series(path, history, metric) for path in baselines]
    forecasts = [{"scenario": "baseline", "points": _points(base, ends, labels, _usd)}]
    changes = []
    for key, alt_paths in paths.items():
        alt = [_series(path, history, metric) for path in alt_paths]
        forecasts.append({"scenario": key, "points": _points(alt, ends, labels, _usd)})
        deltas = [
            [a - b for a, b in zip(ap, bp, strict=True)] for ap, bp in zip(alt, base, strict=True)
        ]
        changes.append(
            {"scenario": key, "unit": "currency", "points": _points(deltas, ends, labels, _usd)}
        )
        # A share of the baseline is only defined while the baseline stays positive (FP-08).
        if all(value > 0 for path in base for value in path):
            shares = [
                [d / b for d, b in zip(dp, bp, strict=True)]
                for dp, bp in zip(deltas, base, strict=True)
            ]
            points = _points(shares, ends, labels, _fraction)
            changes.append({"scenario": key, "unit": "fraction_of_baseline", "points": points})
    label, definition = DEFINITIONS[metric]
    return {
        "metric": metric,
        "label": label,
        "definition": definition,
        "observed": _observed(history, metric),
        "forecasts": forecasts,
        "changes": changes,
    }


def _events(
    as_of: date, alternates: Sequence[Alternate], timings: dict[str, Timing], ends: list[date]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {"on": as_of.isoformat(), "label": "Knowledge cutoff", "kind": "cutoff", "scenario": None}
    ]
    for alt in alternates:
        timing, t = alt.draft.decision.timing, timings[alt.key]
        for on, text, kind in (
            (timing.announcement_date, "announced", "announcement"),
            (timing.effective_date, "takes effect", "effective"),
            (ends[min(t.start, HORIZON - 1)], "effect starts", "effect_start"),
            (ends[min(t.start + t.ramp, HORIZON - 1)], "full effect", "full_effect"),
        ):
            label = f"{alt.label}: {text}"
            events.append({"on": on.isoformat(), "label": label, "kind": kind, "scenario": alt.key})
    return events


def build_result(
    result_id: str,
    title: str,
    dossier: CompanyDossier,
    as_of: date,
    seed: int,
    alternates: Sequence[Alternate],
) -> ScenarioResult:
    history = _history(dossier, as_of)
    calendar = _forecast_calendar(history)
    ends = calendar[0]
    timings = {alt.key: _timing(alt.draft, ends) for alt in alternates}
    baselines, paths, steps = _simulate(history, seed, alternates, timings)

    distributions, waterfalls = [], []
    for alt in alternates:
        for metric in ("revenue", "ebitda"):
            deltas = [
                getattr(a, metric)[-1] - getattr(b, metric)[-1]
                for a, b in zip(paths[alt.key], baselines, strict=True)
            ]
            distributions.append(
                {
                    "metric": metric,
                    "scenario": alt.key,
                    "period_end": ends[-1].isoformat(),
                    "bins": _histogram(deltas),
                    "probability_above_zero": _fraction(sum(d > 0 for d in deltas) / PATHS),
                    "mean": _usd(sum(deltas) / PATHS),
                }
            )
        cumulative = alt.waterfall_aggregation == "cumulative"
        totals = [
            sum(getattr(path, alt.waterfall_metric))
            if cumulative
            else getattr(path, alt.waterfall_metric)[-1]
            for path in baselines
        ]
        start = round(sum(totals) / PATHS)
        rows = [
            {
                "label": name,
                "value": str(round(sum(values) / PATHS)),
                "explanation": STEP_EXPLANATIONS[name],
            }
            for name, values in steps[alt.key].items()
        ]
        waterfalls.append(
            {
                "metric": alt.waterfall_metric,
                "scenario": alt.key,
                "period_end": ends[-1].isoformat(),
                "aggregation": alt.waterfall_aggregation,
                "statistic": "mean",
                "start": str(start),
                "steps": rows,
                # Means add up, so the end is the start plus the rounded steps exactly.
                "end": str(start + sum(int(row["value"]) for row in rows)),
            }
        )

    payload = {
        **_header(result_id, title, dossier, as_of, seed),
        "status": "completed",
        "scenarios": [{"key": "baseline", "label": "Baseline", "decision": None}]
        + [
            {
                "key": alt.key,
                "label": alt.label,
                "decision": alt.draft.decision.model_dump(mode="json"),
            }
            for alt in alternates
        ],
        "metrics": [_metric(m, history, calendar, baselines, paths) for m in DEFINITIONS],
        "distributions": distributions,
        "waterfalls": waterfalls,
        "events": _events(as_of, alternates, timings, ends),
        "failure": None,
    }
    sources = {
        s for name in ("revenue", "ebitda", "fcf", "net_debt") for s in history.sources[name]
    }
    payload["manifest"]["source_ids"] = sorted(sources)
    return ScenarioResult.model_validate_json(json.dumps(payload))


def _header(
    result_id: str, title: str, dossier: CompanyDossier, as_of: date, seed: int
) -> dict[str, Any]:
    cutoff = datetime.combine(as_of, time(23, 59, 59), tzinfo=UTC)
    return {
        "result_id": result_id,
        "title": title,
        "mode": "demo",
        "data_origin": "synthetic",
        "mock": True,
        "company_id": dossier.company.company_id,
        "company_name": dossier.company.names[-1].name,
        "as_of": as_of.isoformat(),
        "currency": "USD",
        "horizon_quarters": HORIZON,
        "paths": PATHS,
        "seed": seed,
        "model": MODEL,
        "uncertainty_type": "conditional_model_quantiles",
        "calibrated": False,
        "manifest": {
            "contracts_version": CONTRACTS_VERSION,
            "scenario_id": result_id,
            "revision": 1,
            "mode": "demo",
            "data_origin": "synthetic",
            "as_of": cutoff.isoformat().replace("+00:00", "Z"),
            "seed": seed,
            "code_version": "mock-generator",
            "model_id": None,
            "dataset_snapshot_id": None,
            "source_ids": [],
            "generated_at": GENERATED_AT,
        },
        "created_at": GENERATED_AT,
    }


def _draft(company_id: str, as_of: date, decision: dict[str, Any]) -> ScenarioDraft:
    payload = {
        "contracts_version": CONTRACTS_VERSION,
        "company_id": company_id,
        "as_of": as_of.isoformat(),
        "data_origin": "synthetic",
        "horizon_quarters": HORIZON,
        "seed": 0,
        "decision": decision,
    }
    return ScenarioDraft.model_validate_json(json.dumps(payload))


def _timing_fields(as_of: date, lag: int, ramp: int) -> dict[str, Any]:
    effective = as_of + timedelta(days=1)
    return {
        "announcement_date": as_of.isoformat(),
        "effective_date": effective.isoformat(),
        "lag_quarters": lag,
        "ramp_quarters": ramp,
    }


def _triangular(low: str, mode: str, high: str) -> dict[str, str]:
    return {"shape": "triangular", "low": low, "mode": mode, "high": high}


def _rnd(share: str, as_of: date) -> dict[str, Any]:
    return {
        "type": "rnd_change",
        "magnitude": {"value": share, "unit": "fraction_of_previous_rnd_budget"},
        "timing": _timing_fields(as_of, 0, 2),
        "capitalized_fraction": "0",
        "adoption_delay_quarters": _triangular("4", "8", "12"),
        "financing": {"cash": "1", "debt": "0", "equity": "0"},
    }


def _capex(amount: str, capacity: str, as_of: date) -> dict[str, Any]:
    return {
        "type": "capex_expansion",
        "magnitude": {"value": amount, "unit": "usd"},
        "timing": _timing_fields(as_of, 4, 4),
        "capacity_increase": capacity,
        "useful_life_years": 20,
        "utilization": _triangular("0.5", "0.75", "0.9"),
        "new_debt_interest_rate": "0.06",
        "financing": {"cash": "0.5", "debt": "0.5", "equity": "0"},
    }


def _workforce(change: str, as_of: date) -> dict[str, Any]:
    return {
        "type": "workforce_restructure",
        "magnitude": {"value": change, "unit": "fraction_of_headcount"},
        "timing": _timing_fields(as_of, 1, 2),
        "payroll_to_revenue": "0.25",
        "one_off_cost_months": _triangular("2", "4", "8"),
        "savings_realization": _triangular("0.5", "0.7", "0.9"),
        "productivity_loss": _triangular("0", "0.03", "0.1"),
        "financing": {"cash": "1", "debt": "0", "equity": "0"},
    }


def failed_result(dossier: CompanyDossier) -> ScenarioResult:
    result_id = "6f1d2b8a-3c4e-4a5f-9b7d-1e2c3a4b5d6e"
    title = "Halcyon debt refinancing (failed run)"
    payload = {
        **_header(result_id, title, dossier, date(2022, 12, 31), 7),
        "status": "failed",
        "failure": {
            "code": "worker_lost",
            "message": (
                "The run stopped before any path finished because the worker was lost. "
                "No partial numbers are shown."
            ),
            "incident_id": "INC-MOCK-0001",
        },
    }
    return ScenarioResult.model_validate_json(json.dumps(payload))


def build_results() -> list[ScenarioResult]:
    dossiers = {spec.company.company_id: build_dossier(spec) for spec in demo_specs()}
    northwind = dossiers[NORTHWIND]
    q4, q2 = date(2022, 12, 31), date(2022, 6, 30)
    rnd_ttm = _history(northwind, q4).rnd_ttm or 0.0

    def rnd(key: str, label: str, share: str) -> Alternate:
        draft = _draft(NORTHWIND, q4, _rnd(share, q4))
        assert isinstance(draft.decision, RndChange)
        return Alternate(
            key, label, draft, rnd_effect(draft.decision, rnd_ttm), "ebitda", "quarter"
        )

    def capex(key: str, label: str, amount: str, capacity: str) -> Alternate:
        draft = _draft(NORTHWIND, q4, _capex(amount, capacity, q4))
        assert isinstance(draft.decision, CapexExpansion)
        return Alternate(key, label, draft, capex_effect(draft.decision), "fcf", "cumulative")

    workforce = _draft(NORTHWIND, q2, _workforce("-0.1", q2))
    assert isinstance(workforce.decision, WorkforceRestructure)
    return [
        build_result(
            "2d7c9e41-5b3a-4f6e-8c1d-9a0b7e6f5c34",
            "Northwind R&D budget +20% and +40%",
            northwind,
            q4,
            20261027,
            [rnd("alt_a", "R&D +20%", "0.2"), rnd("alt_b", "R&D +40%", "0.4")],
        ),
        build_result(
            "8a4f6c2e-1d3b-4e5a-9f7c-2b6d8e0a1c53",
            "Northwind CAPEX USD 0.5bn and USD 1bn",
            northwind,
            q4,
            20261027,
            [
                capex("alt_a", "CAPEX USD 0.5bn", "500000000", "0.15"),
                capex("alt_b", "CAPEX USD 1bn", "1000000000", "0.3"),
            ],
        ),
        build_result(
            "c3e5a7b9-2f4d-4c6e-8a0b-5d7f9e1c3a62",
            "Northwind workforce −10% (cutoff 2022-06-30)",
            northwind,
            q2,
            20261027,
            [
                Alternate(
                    "alt_a",
                    "Headcount −10%",
                    workforce,
                    workforce_effect(workforce.decision),
                    "ebitda",
                    "cumulative",
                )
            ],
        ),
        failed_result(dossiers[HALCYON]),
    ]


def render() -> str:
    results = [json.loads(result.model_dump_json()) for result in build_results()]
    return json.dumps(results, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the fixture file is stale")
    args = parser.parse_args(argv)
    expected = render()
    if args.check:
        current = FIXTURE_PATH.read_text(encoding="utf-8") if FIXTURE_PATH.exists() else ""
        if current != expected:
            print(f"{FIXTURE_PATH.name} is stale. Run: npm run contracts:gen", file=sys.stderr)
            return 1
        print(f"{FIXTURE_PATH.name} is up to date (mock results)")
        return 0
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
