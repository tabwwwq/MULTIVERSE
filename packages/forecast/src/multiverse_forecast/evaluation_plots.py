"""Stage 17 figures as plain SVG, drawn from the scores of the package and nothing else.

Each plot has one axis scale, a legend for two or more series, recessive grid lines and
text in text colors. Marks carry a native tooltip (``<title>``) with the exact value.
"""

import html
from collections.abc import Sequence
from dataclasses import dataclass

from multiverse_contracts.forecasting import (
    AblationScore,
    BandScore,
    EvaluationPackage,
    EvaluationProtocol,
    ForecastTarget,
    Population,
    SplitName,
)

STYLE = (
    "<style>"
    "svg{--surface:#fcfcfb;--ink:#0b0b0b;--muted:#52514e;--grid:#e4e3df;"
    "--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4}"
    "@media (prefers-color-scheme:dark){svg{--surface:#1a1a19;--ink:#f0efec;--muted:#c3c2b7;"
    "--grid:#3a3a37;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181}}"
    "text{font:12px system-ui,sans-serif;fill:var(--muted)}"
    ".title{font-size:15px;font-weight:600;fill:var(--ink)}.ink{fill:var(--ink)}"
    "</style>"
)
SERIES = ("var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)")
TITLES = {
    ForecastTarget.REVENUE_GROWTH: "Revenue growth",
    ForecastTarget.OPERATING_MARGIN: "Operating margin",
    ForecastTarget.EBITDA_MARGIN: "EBITDA margin",
    ForecastTarget.FCF_MARGIN: "FCF margin",
    ForecastTarget.DEBT_TO_EBITDA: "Debt / EBITDA",
}
REPORT_HORIZON = 4


@dataclass(frozen=True)
class Area:
    x: float
    y: float
    width: float
    height: float
    low_x: float
    high_x: float
    low_y: float
    high_y: float

    def px(self, value: float) -> float:
        return self.x + self.width * (value - self.low_x) / (self.high_x - self.low_x)

    def py(self, value: float) -> float:
        return self.y + self.height * (1 - (value - self.low_y) / (self.high_y - self.low_y))


def _open(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(title)}">',
        STYLE,
        '<rect width="100%" height="100%" fill="var(--surface)"/>',
        f'<text class="title" x="16" y="26">{html.escape(title)}</text>',
    ]


def _legend(names: Sequence[str], x: float, y: float) -> list[str]:
    parts: list[str] = []
    for i, name in enumerate(names):
        parts.append(
            f'<rect x="{x:.0f}" y="{y - 9:.0f}" width="12" height="4" rx="2" fill="{SERIES[i]}"/>'
        )
        parts.append(f'<text x="{x + 18:.0f}" y="{y:.0f}">{html.escape(name)}</text>')
        x += 26 + 7.2 * len(name)
    return parts


def _grid(area: Area, ticks: Sequence[float], label: str = "{:.1f}") -> list[str]:
    parts: list[str] = []
    for tick in ticks:
        y = area.py(tick)
        parts.append(
            f'<line x1="{area.x:.1f}" y1="{y:.1f}" x2="{area.x + area.width:.1f}" y2="{y:.1f}" '
            'stroke="var(--grid)"/>'
        )
        parts.append(
            f'<text x="{area.x - 6:.1f}" y="{y + 4:.1f}" text-anchor="end">'
            f"{label.format(tick)}</text>"
        )
    return parts


def _line(
    area: Area, points: Sequence[tuple[float, float]], color: str, tips: Sequence[str]
) -> list[str]:
    path = " ".join(f"{area.px(x):.1f},{area.py(y):.1f}" for x, y in points)
    parts = [f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{path}"/>']
    for (x, y), tip in zip(points, tips, strict=True):
        parts.append(
            f'<circle cx="{area.px(x):.1f}" cy="{area.py(y):.1f}" r="4" fill="{color}" '
            f'stroke="var(--surface)" stroke-width="2"><title>{html.escape(tip)}</title></circle>'
        )
    return parts


def _cell(
    scores: Sequence[BandScore],
    model: str,
    flag: bool,
    target: ForecastTarget,
    horizon: int,
    period: str,
) -> BandScore | None:
    return next(
        (
            s
            for s in scores
            if s.model == model
            and s.calibrated is flag
            and s.target is target
            and s.horizon == horizon
            and s.period == period
            and s.split is SplitName.TEST
            and s.population is Population.ALL
        ),
        None,
    )


def reliability(package: EvaluationPackage, protocol: EvaluationProtocol) -> str:
    """One panel per target: the share of actuals below each quantile, raw and calibrated."""
    width, height, panel, gap = 980, 330, 160, 28
    title = f"Reliability at h={REPORT_HORIZON}, final years: share of actuals below each quantile"
    out = _open(width, height, title)
    out += _legend(("Raw", "Calibrated"), 16, 50)
    for i, target in enumerate(TITLES):
        x = 44 + i * (panel + gap)
        area = Area(x, 84, panel, panel, 0, 1, 0, 1)
        out.append(f'<text class="ink" x="{x}" y="74">{TITLES[target]}</text>')
        out += _grid(area, (0, 0.5, 1) if i == 0 else ())
        for tick in (0, 0.5, 1):
            out.append(
                f'<text x="{area.px(tick):.1f}" y="{area.y + panel + 18:.1f}" '
                f'text-anchor="middle">{tick:g}</text>'
            )
        out.append(
            f'<line x1="{area.px(0):.1f}" y1="{area.py(0):.1f}" x2="{area.px(1):.1f}" '
            f'y2="{area.py(1):.1f}" stroke="var(--muted)" stroke-dasharray="4 4"/>'
        )
        out.append(
            f'<rect x="{x}" y="84" width="{panel}" height="{panel}" fill="none" '
            'stroke="var(--grid)"/>'
        )
        for n, flag in enumerate((False, True)):
            s = _cell(package.scores, package.primary_model, flag, target, REPORT_HORIZON, "final")
            if s is None:
                continue
            points = list(zip(protocol.levels, s.reliability, strict=True))
            tips = [f"level {a}: {100 * b:.1f}% of {s.examples} rows" for a, b in points]
            out += _line(area, points, SERIES[n], tips)
    out.append(
        f'<text x="16" y="{height - 14}">Dashed: perfect calibration. Horizontal: nominal level. '
        "Vertical: observed share.</text>"
    )
    return "\n".join([*out, "</svg>\n"])


def coverage_by_year(package: EvaluationPackage, protocol: EvaluationProtocol) -> str:
    """Coverage of the 80% interval by test year: the calibration against a moving world."""
    width, height = 760, 360
    years = sorted(
        {int(s.value) for s in package.slices if s.kind == "year" and s.horizon == REPORT_HORIZON}
    )
    index = protocol.nominal.index(0.8)
    title = f"80% interval coverage by origin year, h={REPORT_HORIZON}, seen firms"
    out = _open(width, height, title)
    out += _legend(tuple(TITLES.values()), 16, 50)
    area = Area(60, 72, width - 90, height - 120, years[0] - 0.3, years[-1] + 0.3, 0.4, 1.0)
    out += _grid(area, (0.4, 0.6, 0.8, 1.0), "{:.0%}")
    out.append(
        f'<line x1="{area.x}" y1="{area.py(0.8):.1f}" x2="{area.x + area.width}" '
        f'y2="{area.py(0.8):.1f}" stroke="var(--muted)" stroke-dasharray="4 4"/>'
    )
    for year in years:
        out.append(
            f'<text x="{area.px(year):.1f}" y="{area.y + area.height + 18:.1f}" '
            f'text-anchor="middle">{year}</text>'
        )
    for n, target in enumerate(TITLES):
        points: list[tuple[float, float]] = []
        tips: list[str] = []
        for s in package.slices:
            if s.kind == "year" and s.target is target and s.horizon == REPORT_HORIZON:
                points.append((int(s.value), s.coverage[index]))
                share = 100 * s.coverage[index]
                tips.append(f"{TITLES[target]} {s.value}: {share:.1f}% of {s.examples} rows")
        out += _line(area, points, SERIES[n], tips)
    out.append(f'<text x="16" y="{height - 14}">Dashed: nominal 80%.</text>')
    return "\n".join([*out, "</svg>\n"])


def against_persistence(package: EvaluationPackage) -> str:
    """Pinball against the persistence band, by target and horizon, final years."""
    width, row = 760, 22
    rows = [
        (target, horizon)
        for target in TITLES
        for horizon in sorted({s.horizon for s in package.scores if s.period == "final"})
        if _cell(
            package.scores, package.primary_model, package.calibrated, target, horizon, "final"
        )
    ]
    height = 130 + row * len(rows)
    title = "Pinball against the persistence band, final years, seen firms"
    out = _open(width, height, title)
    names = (package.primary_model, "gbm_quantile")
    out += _legend(names, 16, 50)
    values = [
        s.vs_persistence_low
        for t, h in rows
        for m, f in ((names[0], package.calibrated), (names[1], True))
        if (s := _cell(package.scores, m, f, t, h, "final")) and s.vs_persistence_low is not None
    ]
    highs = [
        s.vs_persistence_high
        for t, h in rows
        for m, f in ((names[0], package.calibrated), (names[1], True))
        if (s := _cell(package.scores, m, f, t, h, "final")) and s.vs_persistence_high is not None
    ]
    low = min(-0.1, min(values, default=-0.5))
    high = max(0.1, max(highs, default=0.1))
    area = Area(190, 70, width - 220, row * len(rows), low, high, 0, len(rows))
    out.append(
        f'<line x1="{area.px(0):.1f}" y1="{area.y}" x2="{area.px(0):.1f}" '
        f'y2="{area.y + area.height}" stroke="var(--muted)" stroke-dasharray="4 4"/>'
    )
    for i, (target, horizon) in enumerate(rows):
        y = area.y + row * (i + 0.5)
        out.append(
            f'<text x="{area.x - 8}" y="{y + 4:.1f}" text-anchor="end">'
            f"{TITLES[target]} h={horizon}</text>"
        )
        for n, (model, flag) in enumerate(((names[0], package.calibrated), (names[1], True))):
            s = _cell(package.scores, model, flag, target, horizon, "final")
            if s is None or s.vs_persistence is None:
                continue
            dy = y + (n - 0.5) * 7
            tip = f"{model} {target.value} h={horizon}: {100 * s.vs_persistence:+.1f}%"
            out.append(
                f'<line x1="{area.px(s.vs_persistence_low or 0):.1f}" y1="{dy:.1f}" '
                f'x2="{area.px(s.vs_persistence_high or 0):.1f}" y2="{dy:.1f}" '
                f'stroke="{SERIES[n]}" stroke-width="2"/>'
            )
            out.append(
                f'<circle cx="{area.px(s.vs_persistence):.1f}" cy="{dy:.1f}" r="4" '
                f'fill="{SERIES[n]}" stroke="var(--surface)" stroke-width="2">'
                f"<title>{html.escape(tip)}</title></circle>"
            )
    for tick in (low, 0.0, high):
        out.append(
            f'<text x="{area.px(tick):.1f}" y="{area.y + area.height + 18:.1f}" '
            f'text-anchor="middle">{100 * tick:+.0f}%</text>'
        )
    out.append(
        f'<text x="16" y="{height - 12}">Left of zero: lower pinball than persistence. '
        "Whiskers: 95% interval, bootstrap over firms.</text>"
    )
    return "\n".join([*out, "</svg>\n"])


def ablations(package: EvaluationPackage) -> str:
    """Change of pinball when one input is removed, at one horizon, per target."""
    chosen: list[AblationScore] = [a for a in package.ablations if a.horizon == REPORT_HORIZON]
    names = sorted({a.name for a in chosen})
    width, row = 760, 76
    height = 132 + row * len(names)
    title = f"Pinball change without one input, h={REPORT_HORIZON}, all test years, seen firms"
    out = _open(width, height, title)
    out += _legend(tuple(TITLES.values()), 16, 50)
    low = min([-0.02, *(a.change_low for a in chosen)])
    high = max([0.02, *(a.change_high for a in chosen)])
    area = Area(130, 72, width - 160, row * len(names), low, high, 0, len(names))
    out.append(
        f'<line x1="{area.px(0):.1f}" y1="{area.y}" x2="{area.px(0):.1f}" '
        f'y2="{area.y + area.height}" stroke="var(--muted)" stroke-dasharray="4 4"/>'
    )
    for i, name in enumerate(names):
        center = area.y + row * (i + 0.5)
        out.append(
            f'<text x="{area.x - 8}" y="{center + 4:.1f}" text-anchor="end">'
            f"{html.escape(name)}</text>"
        )
        for n, target in enumerate(TITLES):
            a = next((a for a in chosen if a.name == name and a.target is target), None)
            if a is None:
                continue
            dy = center + (n - 2) * 11
            tip = f"{name} {target.value}: {100 * a.change:+.1f}% ({a.examples} rows)"
            out.append(
                f'<line x1="{area.px(a.change_low):.1f}" y1="{dy:.1f}" '
                f'x2="{area.px(a.change_high):.1f}" y2="{dy:.1f}" stroke="{SERIES[n]}" '
                'stroke-width="2"/>'
            )
            out.append(
                f'<circle cx="{area.px(a.change):.1f}" cy="{dy:.1f}" r="4" fill="{SERIES[n]}" '
                f'stroke="var(--surface)" stroke-width="2">'
                f"<title>{html.escape(tip)}</title></circle>"
            )
    for tick in (low, 0.0, high):
        out.append(
            f'<text x="{area.px(tick):.1f}" y="{area.y + area.height + 18:.1f}" '
            f'text-anchor="middle">{100 * tick:+.1f}%</text>'
        )
    out.append(
        f'<text x="16" y="{height - 12}">Right of zero: the model needs that input. '
        "Whiskers: 95% interval, bootstrap over firms.</text>"
    )
    return "\n".join([*out, "</svg>\n"])


def plots(package: EvaluationPackage, protocol: EvaluationProtocol) -> dict[str, str]:
    return {
        "reliability.svg": reliability(package, protocol),
        "coverage-by-year.svg": coverage_by_year(package, protocol),
        "against-persistence.svg": against_persistence(package),
        "ablations.svg": ablations(package),
    }
