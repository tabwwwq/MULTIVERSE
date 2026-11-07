"""A real case from local data: the warehouse, the forecasting dataset and the signed model.

Everything read here was public at the origin. Rows of the history end at the origin, the panel
stops at the cutoff, and the model median comes from a fold that never saw these years. GDP growth
comes from the World Bank as known on the day of the case: it has no dated vintages, so a history
of it is fair for a case of today and has no place among the features of the model.

The warehouse has no PP&E, goodwill, working capital or interest. What it lacks is implied or
assumed, and each input says which. A case is an honest sketch of a company, not its books.

Many large filers tag no EBITDA parts: Exxon Mobil and Eli Lilly file no operating income, Microsoft
no quarterly D&A. Such a case stands on the nearest figure they do file, and says so.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np

from multiverse_contracts.primitives import DataOrigin
from multiverse_contracts.simulation import (
    CapitalInputs,
    CaseDrivers,
    CaseHistoryPoint,
    CaseInput,
    CaseOpening,
    CasePolicy,
    CaseTranche,
    CentralPath,
    ShockHistory,
    ShockRow,
    SimulationCase,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_forecast.data import Dataset
from multiverse_pipelines.pit.clock import day_end
from multiverse_pipelines.pit.panel import build_panel
from multiverse_pipelines.pit.warehouse import Warehouse
from multiverse_simulation.shocks import Floats

METRICS = (
    "revenue",
    "cogs",
    "rnd",
    "ebitda",
    "operating_income",
    "cfo",
    "depreciation_amortization",
    "free_cash_flow",
    "capex",
    "cash",
    "long_term_debt",
    "long_term_debt_noncurrent",
    "debt_current",
)
SIGNED_HORIZONS = (4, 8)
"""EBITDA margin pairs of the signed model (`model-20261028-9ce4d4180aa9`): research only."""
MEDIAN_LEVEL = 3
WINSOR = 0.01
MIN_ROWS = 16
"""Four years of shocks: fewer, and a block draw would mostly repeat itself."""
MARGINS = (
    ("ebitda_margin_l1", "EBITDA margin"),
    ("op_margin_l1", "operating margin"),
    ("fcf_margin_l1", "free cash flow margin"),
)
"""The margin whose shocks a firm can show, nearest to EBITDA first."""
BASES = {
    "ebitda": None,
    "operating_income": "No EBITDA in the filings: operating income plus D&A stands for it.",
    "cfo": "No operating income in the filings: cash from operations stands for EBITDA.",
}
COGS_SHARE = 0.5
"""Of cash costs other than R&D, for a filer that reports no cost of revenue."""
MEAN_BLOCK = 4.0
HORIZON = 20
HISTORY = 8

TAX = "0.23"
DEPRECIATION = Decimal("0.125")
NWC_RATIO = 0.12
SPREAD = Decimal("0.02")
FLOATING_SHARE = Decimal("0.30")
MIN_CASH_SHARE = Decimal("0.02")
REVOLVER_SHARE = Decimal("0.05")
PAYOUT = "0.25"
ERP = "0.05"
BETA = "1.0"
DEBT_WEIGHT = "0.15"
TERMINAL_GROWTH = "0.025"


@dataclass(frozen=True)
class Series:
    """A firm by quarter, innovations of an AR(1) on its demeaned series."""

    quarters: np.ndarray
    growth: Floats
    margin: Floats
    persistence_growth: float
    persistence_margin: float


def _column(ds: Dataset, name: str) -> Floats:
    return ds.x[:, ds.features.index(name)]


def _matrix(ds: Dataset, rows: np.ndarray, column: Floats) -> tuple[Floats, np.ndarray, list[str]]:
    """Firms by quarters of one column, for the given rows of the dataset."""
    ciks = sorted(set(ds.ciks[rows].tolist()))
    quarters = np.unique(ds.origins[rows])
    place = {cik: index for index, cik in enumerate(ciks)}
    where = {quarter: index for index, quarter in enumerate(quarters)}
    grid = np.full((len(ciks), len(quarters)), np.nan)
    for row in rows:
        grid[place[str(ds.ciks[row])], where[ds.origins[row]]] = column[row]
    return grid, quarters, ciks


def _row_mean(grid: Floats) -> Floats:
    """Mean of each row over its known values; NaN for a row with none, without a warning."""
    known = np.isfinite(grid)
    counts = known.sum(axis=1, keepdims=True)
    totals = np.where(known, grid, 0.0).sum(axis=1, keepdims=True)
    mean: Floats = np.divide(totals, counts, out=np.full(counts.shape, np.nan), where=counts > 0)
    return mean


def _deseasonalized(grid: Floats, quarters: np.ndarray) -> Floats:
    """Less the firm's mean for each quarter of the year: a season is not a shock."""
    months = quarters.astype("datetime64[M]").astype(np.int64) % 12
    out = grid.copy()
    for month in np.unique(months):
        columns = months == month
        out[:, columns] = grid[:, columns] - _row_mean(grid[:, columns])
    return out


def _winsorized(values: Floats) -> Floats:
    low, high = np.nanquantile(values, (WINSOR, 1 - WINSOR))
    return np.clip(values, low, high)


def _innovations(grid: Floats) -> tuple[Floats, float]:
    """ε_t = y_t − φ y_{t−1} on demeaned series, with one pooled φ, kept between 0 and 0.95."""
    centred = _winsorized(grid - _row_mean(grid))
    now, before = centred[:, 1:], centred[:, :-1]
    both = np.isfinite(now) & np.isfinite(before)
    persistence = float((now[both] * before[both]).sum() / (before[both] ** 2).sum())
    persistence = min(max(persistence, 0.0), 0.95)
    return now - persistence * before, persistence


def _margin_of(ds: Dataset, cik: str, day: np.datetime64) -> tuple[str, str, bool]:
    """The margin a firm has enough quarters of. Without one it moves with its sector alone."""
    own = (ds.ciks == cik) & (ds.origins <= day)
    for feature, label in MARGINS:
        if feature in ds.features and np.isfinite(_column(ds, feature)[own]).sum() > MIN_ROWS:
            return feature, label, True
    feature, label = MARGINS[0]
    return feature, f"sector {label} only", False


def central_margins(
    medians: Mapping[str, Mapping[int, float]],
    d_and_a_share: float,
    capex_share: float,
    last_margin: float,
) -> tuple[float, float, str | None]:
    """EBITDA margin at 4 and 8 quarters: of the model, or built from what it forecasts."""
    first, second = SIGNED_HORIZONS
    for target, extra, note in (
        ("ebitda_margin", 0.0, None),
        ("operating_margin", d_and_a_share, "Model operating margin plus D&A share of revenue."),
        ("fcf_margin", capex_share, "Model free cash flow margin plus capex share of revenue."),
    ):
        found = medians.get(target, {})
        if first in found and second in found:
            return found[first] + extra, found[second] + extra, note
    return last_margin, last_margin, "No model margin: the last four quarters held flat."


def gdp_of(gdp: Mapping[int, float], year: int) -> float:
    """Annual growth of a year, or of the last year published while it is still running."""
    known = [item for item in gdp if item <= year]
    return gdp[max(known)] if known else float("nan")


def shock_history(ds: Dataset, cik: str, origin: date, gdp: Mapping[int, float]) -> ShockHistory:
    """Macro, sector and firm columns of every quarter up to the origin; ``gdp`` is by year."""
    division = ds.divisions[ds.ciks == cik][0]
    day = np.datetime64(origin, "D")
    rows = np.flatnonzero((ds.divisions == division) & (ds.origins <= day))
    growth, quarters, ciks = _matrix(ds, rows, _column(ds, "rev_growth_l1"))
    feature, label, own_margin = _margin_of(ds, cik, day)
    margin, _, _ = _matrix(ds, rows, _column(ds, feature))
    margin = _deseasonalized(margin, quarters)
    growth_shocks, persistence_growth = _innovations(growth)
    margin_shocks, persistence_margin = _innovations(margin)
    sector_growth = np.nanmedian(growth_shocks, axis=0)
    sector_margin = np.nanmedian(margin_shocks, axis=0)

    index = ciks.index(cik)
    firm_growth = growth_shocks[index] - sector_growth
    firm_margin = margin_shocks[index] - sector_margin
    if not own_margin:
        firm_margin = np.zeros_like(sector_margin)

    all_rows = np.flatnonzero(ds.origins <= day)
    macro: dict[np.datetime64, tuple[float, float]] = {}
    rates = _column(ds, "macro_ust3m")
    for row in all_rows:
        year = int(ds.origins[row].astype("datetime64[Y]").astype(np.int64)) + 1970
        macro[ds.origins[row]] = (float(rates[row]) / 100, gdp_of(gdp, year) / 100)
    kept: list[ShockRow] = []
    for column, quarter in enumerate(quarters[1:]):
        before = macro.get(quarters[column])
        now = macro.get(quarter)
        values = (firm_growth[column], firm_margin[column])
        if before is None or now is None or not np.isfinite(values).all():
            continue
        if not np.isfinite([*before, *now]).all():
            continue
        kept.append(
            ShockRow(
                quarter_end=quarter.astype("datetime64[D]").astype(date),
                values=(
                    round(now[0] - before[0], 6),
                    round(now[1] - before[1], 6),
                    round(float(sector_growth[column]), 6),
                    round(float(firm_growth[column]), 6),
                    round(float(sector_margin[column]), 6),
                    round(float(firm_margin[column]), 6),
                ),
            )
        )
    if len(kept) < MIN_ROWS:
        raise ValueError(f"{cik}: {len(kept)} quarters of shocks, {MIN_ROWS} are needed")
    short_rate = macro[day][0]
    return ShockHistory(
        variables=(
            "rate_change",
            "gdp_change",
            "sector_growth",
            "firm_growth",
            "sector_margin",
            "firm_margin",
        ),
        rows=tuple(kept),
        persistence_growth=round(persistence_growth, 4),
        persistence_margin=round(persistence_margin, 4),
        mean_block_quarters=MEAN_BLOCK,
        base_short_rate=round(max(short_rate, 0.0), 5),
        peers=len(ciks),
        method=(
            "Innovations of a pooled AR(1) on firm-demeaned symmetric growth and on "
            f"deseasonalized {label}, winsorized at 1%. Sector columns are the cross-section "
            f"median of division {division}; firm columns are what remains. Macro columns are "
            "quarterly changes of the 3-month Treasury yield and of annual GDP growth "
            "(World Bank, CC BY 4.0). Rows end at the origin."
        ),
    )


def _cells(
    warehouse: Warehouse, cik: str, origin: date
) -> dict[tuple[str, int], tuple[Decimal, object]]:
    panel = build_panel(warehouse, [cik], day_end(origin), quarters=HISTORY + 6, metrics=METRICS)
    return {
        (cell.metric, cell.lag): (Decimal(cell.value), cell)
        for cell in panel.cells
        if cell.mask and cell.value is not None
    }


def _text(value: Decimal) -> str:
    return f"{value:.2f}"


def build_case(
    warehouse: Warehouse,
    ds: Dataset,
    medians: Mapping[str, Mapping[int, float]],
    cik: str,
    name: str,
    origin: date,
    model_id: str,
    gdp: Mapping[int, float],
    as_of: date | None = None,
) -> SimulationCase:
    """``medians`` are the margins of the model by target and horizon. ``as_of`` is the day of the
    data when the origin is the quarter end after it."""
    cells = _cells(warehouse, cik, origin)
    lags = sorted({lag for metric, lag in cells if metric == "revenue" and lag >= 1})
    if lags[:4] != [1, 2, 3, 4]:
        raise ValueError(f"{cik}: the last four quarters of revenue are not known at {origin}")

    def get(metric: str, lag: int) -> Decimal | None:
        found = cells.get((metric, lag))
        return found[0] if found is not None else None

    def need(metric: str, lag: int) -> Decimal:
        value = get(metric, lag)
        if value is None:
            raise ValueError(f"{cik}: {metric} is not known at lag {lag}")
        return value

    def debt_at(lag: int) -> Decimal | None:
        total = get("long_term_debt", lag)
        if total is not None:
            return total
        noncurrent = get("long_term_debt_noncurrent", lag)
        if noncurrent is None:
            return None
        return noncurrent + (get("debt_current", lag) or Decimal(0))

    year = (1, 2, 3, 4)

    def filed(metric: str) -> bool:
        return all(get(metric, k) is not None for k in year)

    def total(metric: str) -> Decimal:
        return sum((need(metric, k) for k in year), Decimal(0))

    basis = next((metric for metric in BASES if filed(metric)), None)
    if basis is None:
        raise ValueError(f"{cik}: no earnings of any kind for the last four quarters at {origin}")
    has_d_and_a, has_capex = filed("depreciation_amortization"), filed("capex")
    if not has_d_and_a and not has_capex:
        raise ValueError(f"{cik}: neither D&A nor capex for the last four quarters at {origin}")
    revenue = total("revenue")
    d_and_a = total("depreciation_amortization") if has_d_and_a else total("capex")
    capex = total("capex") if has_capex else d_and_a
    ebitda = total(basis) + (d_and_a if basis == "operating_income" else Decimal(0))
    has_cogs = filed("cogs")

    def earnings(lag: int) -> Decimal:
        return need(basis, lag) + (d_and_a / 4 if basis == "operating_income" else Decimal(0))

    cogs = sum((get("cogs", k) or Decimal(0) for k in year), Decimal(0))
    rnd = sum((get("rnd", k) or Decimal(0) for k in year), Decimal(0))
    cash = need("cash", 1)
    filed_debt = debt_at(1)
    debt = filed_debt if filed_debt is not None else Decimal(0)
    assumed: list[CaseInput] = []
    note = BASES[basis]
    if note is not None:
        assumed.append(CaseInput(name="ebitda_basis", origin="assumed", note=note))
    if not has_d_and_a:
        assumed.append(
            CaseInput(
                name="d_and_a_missing",
                origin="assumed",
                note="No quarterly D&A in the filings: capital expenditure stands for it.",
            )
        )
    if not has_capex:
        assumed.append(
            CaseInput(
                name="capex_missing",
                origin="assumed",
                note="No capital expenditure in the filings: D&A stands for it.",
            )
        )
    if filed_debt is None:
        assumed.append(
            CaseInput(
                name="debt_missing", origin="assumed", note="No debt in the filings: zero assumed."
            )
        )
    if not has_cogs:
        assumed.append(
            CaseInput(
                name="cogs_missing",
                origin="assumed",
                note="No cost of revenue in the filings: half of cash costs assumed.",
            )
        )

    shocks = shock_history(ds, cik, origin, gdp)
    short_rate = Decimal(str(shocks.base_short_rate))
    rate = short_rate + SPREAD
    floating = debt * FLOATING_SHARE
    rate_text = f"{rate:.4f}"
    cash_costs = revenue - ebitda - rnd
    cash_cogs = max(cogs - d_and_a, Decimal(0))
    last_margin = float(ebitda / revenue)
    at_first, at_second, margin_note = central_margins(
        medians, float(d_and_a / revenue), float(capex / revenue), last_margin
    )
    if margin_note is not None:
        assumed.append(CaseInput(name="margin_source", origin="assumed", note=margin_note))

    # Quarter 1 of the path is the quarter that ended at the origin: reported later.
    margins = np.interp(
        np.arange(1, HORIZON + 1),
        (1, SIGNED_HORIZONS[0] + 1, SIGNED_HORIZONS[1] + 1),
        (last_margin, at_first, at_second),
    )
    row = np.flatnonzero((ds.ciks == cik) & (ds.origins == np.datetime64(origin, "D")))[0]
    start_growth = float(_column(ds, "rev_growth_l1")[row])
    own = (ds.ciks == cik) & (ds.origins <= np.datetime64(origin, "D"))
    usual = float(np.nanmean(_column(ds, "rev_growth_l1")[own]))
    decay = shocks.persistence_growth ** np.arange(1, HORIZON + 1)
    growth = usual + decay * (start_growth - usual)

    points = []
    for lag in range(HISTORY, 0, -1):
        found = cells.get(("revenue", lag))
        if found is None:
            continue
        cell = found[1]
        earlier_debt, earlier_cash = debt_at(lag), get("cash", lag)
        points.append(
            CaseHistoryPoint(
                period_end=cell.quarter_end,  # type: ignore[attr-defined]
                fiscal_label=f"{cell.quarter_end.year} Q{(cell.quarter_end.month - 1) // 3 + 1}",  # type: ignore[attr-defined]
                filed_at=cell.known_from.date(),  # type: ignore[attr-defined]
                source_id=f"sec:{cell.accession}",  # type: ignore[attr-defined]
                revenue=_text(found[0]),
                ebitda=_text(need("ebitda", lag)) if get("ebitda", lag) is not None else None,
                fcf=_text(need("free_cash_flow", lag))
                if get("free_cash_flow", lag) is not None
                else None,
                net_debt=_text(earlier_debt - earlier_cash)
                if earlier_debt is not None and earlier_cash is not None
                else None,
            )
        )
    quarterly_interest = debt * rate / 4
    treasury = float(_column(ds, "macro_ust10y")[row]) / 100
    balance_date = cells[("revenue", 1)][1].quarter_end  # type: ignore[attr-defined]
    return SimulationCase(
        contracts_version=CONTRACTS_VERSION,
        case_id=f"case-{cik.lstrip('0')}-{as_of or origin:%Y%m%d}",
        company_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"sec:{cik}")),
        company_name=name,
        as_of=as_of or origin,
        balance_date=balance_date,
        currency="USD",
        data_origin=DataOrigin.EMPIRICAL,
        dataset_id=ds.manifest.dataset_id,
        dataset_sha256=ds.manifest.sha256,
        model_id=model_id,
        opening=CaseOpening(
            cash=_text(cash),
            trade_nwc=_text(revenue * Decimal(str(NWC_RATIO))),
            ppe=_text(d_and_a / DEPRECIATION),
            intangibles="0",
            goodwill="0",
            non_operating_assets="0",
            tranches=(
                CaseTranche(
                    name="fixed_debt", principal=_text(debt - floating), annual_rate=rate_text
                ),
                CaseTranche(
                    name="floating_debt",
                    principal=_text(floating),
                    annual_rate=rate_text,
                    floating=True,
                ),
            ),
            trailing_ebitda=tuple(_text(earnings(k)) for k in (3, 2, 1)),
            trailing_interest=(_text(quarterly_interest),) * 3,
        ),
        policy=CasePolicy(
            tax_rate=TAX,
            depreciation_rate=str(DEPRECIATION),
            amortization_rate="0",
            cash_yield=f"{short_rate:.4f}",
            minimum_cash=_text(revenue * MIN_CASH_SHARE),
            revolver_limit=_text(revenue * REVOLVER_SHARE),
            revolver_rate=f"{short_rate + SPREAD:.4f}",
            marginal_debt_rate=f"{short_rate + SPREAD:.4f}",
            dividend_payout=PAYOUT,
            max_leverage="3.5",
            min_interest_cover="3",
        ),
        drivers=CaseDrivers(
            last_year_revenue=tuple(_text(need("revenue", k)) for k in (4, 3, 2, 1)),
            rd_ratio=round(float(rnd / revenue), 5),
            cogs_share=round(min(float(cash_cogs / cash_costs), 1.0), 5)
            if has_cogs and cash_costs > 0
            else COGS_SHARE,
            capex_ratio=round(float(capex / revenue), 5),
            nwc_ratio=NWC_RATIO,
        ),
        central=CentralPath(
            growth=tuple(round(float(value), 5) for value in growth),
            margin=tuple(round(float(value), 5) for value in margins),
            growth_source=(
                "Transparent rule: the last reported growth decays to the firm's own mean, at the "
                "persistence of the shocks. Growth is not signed for any use."
            ),
            margin_source=(
                f"Median of {model_id} at 4 and 8 quarters, research only; straight lines "
                "from the last four quarters, flat after 8 quarters."
            ),
        ),
        shocks=shocks,
        capital=CapitalInputs(
            risk_free=f"{treasury:.4f}",
            equity_risk_premium=ERP,
            beta=BETA,
            pre_tax_cost_of_debt=f"{treasury + float(SPREAD):.4f}",
            tax_rate=TAX,
            debt_weight=DEBT_WEIGHT,
            terminal_growth=TERMINAL_GROWTH,
        ),
        inputs=(*_inputs(), *assumed),
        history=tuple(points),
    )


def _inputs() -> tuple[CaseInput, ...]:
    return (
        CaseInput(name="revenue", origin="observed", note="SEC filings public at the cutoff."),
        CaseInput(name="ebitda", origin="observed", note="Operating income + D&A, calculated."),
        CaseInput(name="cash", origin="observed", note="Last balance sheet public at the cutoff."),
        CaseInput(name="debt", origin="observed", note="Last balance sheet public at the cutoff."),
        CaseInput(name="capex_ratio", origin="observed", note="Last four quarters."),
        CaseInput(
            name="rd_ratio", origin="observed", note="Last four quarters; 0 if not reported."
        ),
        CaseInput(
            name="ebitda_margin_path",
            origin="model",
            note="Model median at 4 and 8 quarters, research only; interpolated, then flat.",
        ),
        CaseInput(
            name="growth_path",
            origin="assumed",
            note="Transparent rule; the model is not signed for growth.",
        ),
        CaseInput(
            name="ppe", origin="implied", note="D&A of the last year over an assumed 12.5% rate."
        ),
        CaseInput(
            name="trade_nwc",
            origin="assumed",
            note="12% of annualized revenue: the warehouse holds no working capital.",
        ),
        CaseInput(
            name="goodwill",
            origin="assumed",
            note="Zero: not in the warehouse. It moves book equity and gains, not cash.",
        ),
        CaseInput(
            name="interest_rate",
            origin="assumed",
            note="3-month Treasury + 2 points, 30% floating: interest is not in the warehouse.",
        ),
        CaseInput(
            name="liquidity",
            origin="assumed",
            note="Minimum cash 2% and revolver 5% of revenue; covenants 3.5x and 3x.",
        ),
        CaseInput(
            name="deal_accounting",
            origin="assumed",
            note="The target moves with the company; 15% PP&E, 25% intangibles over 10 years.",
        ),
        CaseInput(name="tax_rate", origin="assumed", note="23%."),
        CaseInput(name="dividend_payout", origin="assumed", note="25% of net income."),
        CaseInput(
            name="capital_cost",
            origin="assumed",
            note="ERP 5%, beta 1, debt weight 15%, growth 2.5%; 10-year Treasury observed.",
        ),
    )
