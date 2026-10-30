"""The registered macro series: what each measures and how it is published (docs/04).

This is the metadata catalog of Stage 13 and the macro feature plan the owner decides
on (decisions D-11 and D-12). Publication lags and revision cadences describe the
publishers' practice as documented on 2026-10-29; the pipeline does not rely on them for
availability when a source gives real-time data (FRED/ALFRED).
"""

from multiverse_contracts.macro import (
    Frequency,
    MacroSeries,
    SeasonalAdjustment,
    Transform,
    VintageSupport,
)

FRED_ATTRIBUTION = (
    "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve "
    "Bank of St. Louis."
)
ECB_ATTRIBUTION = "Source: ECB statistics."
WB_ATTRIBUTION = "Source: World Bank, World Development Indicators (CC BY 4.0)."
MONTH_START = "first day of the month (FRED convention)"
US_EASTERN = "America/New_York"


def _fred(
    code: str,
    title: str,
    frequency: Frequency,
    unit: str,
    adjustment: SeasonalAdjustment,
    lag: str,
    revisions: str,
    days: str,
    feature: str,
    transform: Transform,
    label: str = MONTH_START,
    notes: str | None = None,
    support: VintageSupport = VintageSupport.FULL,
) -> MacroSeries:
    return MacroSeries(
        series_id=f"fred:{code}",
        source_id="fred-alfred",
        dataset_id="fred-series-observations",
        title=title,
        geography="US",
        frequency=frequency,
        unit=unit,
        seasonal_adjustment=adjustment,
        period_label=label,
        release_timezone=US_EASTERN,
        publication_lag=lag,
        revision_cadence=revisions,
        business_days=days,
        vintage_support=support,
        feature=feature,
        transform=transform,
        attribution=FRED_ATTRIBUTION,
        notes=notes,
    )


def _ecb(
    code: str,
    title: str,
    unit: str,
    lag: str,
    feature: str,
    notes: str,
) -> MacroSeries:
    return MacroSeries(
        series_id=f"ecb:{code}",
        source_id="ecb-data-portal",
        dataset_id="ecb-series",
        title=title,
        geography="EA",
        frequency=Frequency.DAILY,
        unit=unit,
        seasonal_adjustment=SeasonalAdjustment.NOT_APPLICABLE,
        period_label="the business day itself (TIME_PERIOD)",
        release_timezone="Europe/Frankfurt (CET/CEST)",
        publication_lag=lag,
        revision_cadence="Not revised: market fixings and policy decisions",
        business_days="TARGET business days only; no value on weekends and TARGET holidays",
        vintage_support=VintageSupport.NONE,
        feature=feature,
        transform=Transform.END_OF_PERIOD,
        attribution=ECB_ATTRIBUTION,
        notes=notes,
    )


def _wb(code: str, area: str, iso: str, title: str, unit: str, feature: str) -> MacroSeries:
    return MacroSeries(
        series_id=f"wb:{iso}.{code}",
        source_id="world-bank",
        dataset_id="wb-wdi",
        title=f"{title}, {area}",
        geography=iso,
        frequency=Frequency.ANNUAL,
        unit=unit,
        seasonal_adjustment=SeasonalAdjustment.NOT_APPLICABLE,
        period_label="calendar year",
        release_timezone=US_EASTERN,
        publication_lag="First in the WDI update after the year, usually 6 to 12 months later",
        revision_cadence="Irregular database updates (often July, December); past years revised",
        business_days="Not applicable (annual)",
        vintage_support=VintageSupport.ARCHIVE,
        feature=feature,
        transform=Transform.LATEST_YEAR,
        attribution=WB_ATTRIBUTION,
        notes="Availability from dated snapshots (lastupdated); WDI archives give older versions.",
    )


ALL_DAYS = "Monthly average of business days, published once per month"
DAILY_NOTE = (
    "Not revised. ALFRED gives at most 2000 vintage dates per request and a daily series has "
    "thousands, so current values are used, available by the H.15 publication rule."
)
SERIES: tuple[MacroSeries, ...] = (
    _fred(
        "FEDFUNDS",
        "Federal funds effective rate, monthly average",
        Frequency.MONTHLY,
        "percent",
        SeasonalAdjustment.NOT_ADJUSTED,
        "About 1 business day after the month",
        "Practically not revised",
        ALL_DAYS,
        "us_policy_rate",
        Transform.QUARTER_MEAN,
    ),
    _fred(
        "CPIAUCSL",
        "Consumer price index, all urban consumers",
        Frequency.MONTHLY,
        "index 1982-1984 = 100",
        SeasonalAdjustment.ADJUSTED,
        "About 2 weeks after the month (BLS, 8:30 a.m. Eastern)",
        "Seasonal factors revised each February for 5 years",
        "Monthly",
        "us_cpi_inflation",
        Transform.YOY_LAST_MONTH,
    ),
    _fred(
        "UNRATE",
        "Unemployment rate",
        Frequency.MONTHLY,
        "percent",
        SeasonalAdjustment.ADJUSTED,
        "First Friday after the month (BLS, 8:30 a.m. Eastern)",
        "Seasonal factors revised each January for 5 years",
        "Monthly; reference week includes the 12th",
        "us_unemployment",
        Transform.QUARTER_MEAN,
    ),
    _fred(
        "GDPC1",
        "Real gross domestic product",
        Frequency.QUARTERLY,
        "billions of chained 2017 dollars",
        SeasonalAdjustment.ADJUSTED_ANNUAL_RATE,
        "Advance estimate about 30 days after the quarter (BEA, 8:30 a.m. Eastern)",
        "Second and third estimates in the next two months; annual revisions each "
        "September; comprehensive revisions every few years",
        "Quarterly",
        "us_real_gdp_growth",
        Transform.YOY_QUARTER,
        label="first day of the quarter (FRED convention)",
    ),
    _fred(
        "DGS10",
        "Market yield on 10-year Treasury securities, constant maturity",
        Frequency.DAILY,
        "percent",
        SeasonalAdjustment.NOT_ADJUSTED,
        "Next business day (H.15)",
        "Not revised",
        "US government securities business days; no value on holidays",
        "us_10y_yield",
        Transform.END_OF_PERIOD,
        label="the business day itself",
        notes=DAILY_NOTE,
        support=VintageSupport.NONE,
    ),
    _fred(
        "T10Y2Y",
        "10-year minus 2-year Treasury constant maturity",
        Frequency.DAILY,
        "percentage points",
        SeasonalAdjustment.NOT_ADJUSTED,
        "Next business day",
        "Not revised",
        "US government securities business days",
        "us_yield_curve_10y2y",
        Transform.END_OF_PERIOD,
        label="the business day itself",
        notes=DAILY_NOTE,
        support=VintageSupport.NONE,
    ),
    _fred(
        "USREC",
        "NBER based recession indicator",
        Frequency.MONTHLY,
        "1 = recession month, 0 = expansion",
        SeasonalAdjustment.NOT_APPLICABLE,
        "Current months are published as 0 until the NBER dates a turning point",
        "Revised when the NBER announces a peak or trough, often 6 to 18 months later",
        "Monthly",
        "us_recession",
        Transform.QUARTER_MAX,
        notes="The classic look-ahead trap: today's series marks 2020-03 as recession; "
        "the vintage of April 2020 did not.",
    ),
    _ecb(
        "EXR.D.USD.EUR.SP00.A",
        "Euro foreign exchange reference rate, US dollar per euro",
        "US dollars per euro",
        "Same day, around 16:00 CET",
        "eurusd",
        "Reference rates are for information; they are never revised.",
    ),
    _ecb(
        "FM.D.U2.EUR.4F.KR.DFR.LEV",
        "ECB deposit facility rate",
        "percent",
        "Announced before it takes effect",
        "ecb_deposit_rate",
        "Dated by the day it applies; announced at a monetary policy meeting before.",
    ),
    _ecb(
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
        "Euro area AAA government bond yield curve, 10-year spot rate",
        "percent",
        "Next TARGET business day, around 12:00 CET",
        "ea_10y_yield",
        "Svensson model estimate on AAA-rated central government bonds.",
    ),
    *(
        _wb(code, area, iso, title, unit, f"wb_{iso.lower()}_{name}")
        for iso, area in (("USA", "United States"), ("EMU", "Euro area"))
        for code, title, unit, name in (
            ("NY.GDP.MKTP.KD.ZG", "GDP growth", "annual percent", "gdp_growth"),
            ("FP.CPI.TOTL.ZG", "Inflation, consumer prices", "annual percent", "inflation"),
            (
                "SL.UEM.TOTL.ZS",
                "Unemployment, total (ILO estimate)",
                "percent of labour force",
                "unemployment",
            ),
            ("NY.GDP.PCAP.KD", "GDP per capita", "constant 2015 US dollars", "gdp_per_capita"),
        )
    ),
)

BY_ID = {series.series_id: series for series in SERIES}
SOURCES = ("fred-alfred", "ecb-data-portal", "world-bank")
