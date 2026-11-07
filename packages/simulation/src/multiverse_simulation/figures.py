"""Figures of the case studies (Stage 25): plain SVG from finished runs, nothing computed again.

Each figure has a title, a description for screen readers, direct labels and a white background,
so it reads the same on paper, on GitHub in light or dark mode, and without colour.
"""

from collections.abc import Sequence
from decimal import Decimal
from html import escape

from multiverse_contracts.simulation import SimulationReport

WIDTH, HEIGHT = 760, 420
LEFT, RIGHT, TOP, BOTTOM = 84, 190, 56, 56
INK, MUTED, GRID = "#1f2328", "#57606a", "#d0d7de"
BASELINE = "#6e7781"
VARIANTS = ("#0969da", "#bc4c00")
"""Blue and orange: apart for every common colour vision deficiency, and each line is labelled."""
DASHES = ("", "6 4")


def _billions(value: str | None) -> float | None:
    return None if value is None else float(Decimal(value) / Decimal(10**9))


def _frame(title: str, description: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img" aria-labelledby="t d" '
        'font-family="system-ui, -apple-system, Segoe UI, sans-serif">',
        f'<title id="t">{escape(title)}</title>',
        f'<desc id="d">{escape(description)}</desc>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
        f'<text x="{LEFT}" y="28" font-size="16" font-weight="600" fill="{INK}">'
        f"{escape(title)}</text>",
    ]


def _ticks(low: float, high: float, count: int = 5) -> list[float]:
    span = high - low or 1.0
    raw = span / count
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 0.1
    step = max(round(raw / magnitude) * magnitude, magnitude)
    start = (low // step) * step
    found, value = [], start
    while value <= high + step / 2:
        found.append(round(value, 6))
        value += step
    return found


def fan_chart(
    runs: Sequence[tuple[str, SimulationReport]], metric: str, title: str, unit: str = "USD bn"
) -> str:
    """Median and p10 to p90 of one metric: the baseline once, then each variant's decision."""
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    series: list[tuple[str, str, str, list[tuple[float, float, float]]]] = []
    first = runs[0][1]
    labels: list[str] = []
    for index, (label, report) in enumerate(runs):
        found = next(m for m in report.result.metrics if m.metric.value == metric)
        for forecast in found.forecasts:
            if forecast.scenario == "baseline" and index > 0:
                continue
            points = [
                (_billions(p.p10) or 0.0, _billions(p.p50) or 0.0, _billions(p.p90) or 0.0)
                for p in forecast.points
            ]
            labels = [p.fiscal_label for p in forecast.points]
            if forecast.scenario == "baseline":
                series.append(("Baseline", BASELINE, "2 3", points))
            else:
                series.append((label, VARIANTS[index % 2], DASHES[index % 2], points))
    values = [v for *_, pts in series for point in pts for v in point]
    low, high = min(values), max(values)
    ticks = _ticks(low, high)
    low, high = min(low, ticks[0]), max(high, ticks[-1])
    quarters = len(series[0][3])

    def x(i: int) -> float:
        return LEFT + plot_w * i / max(quarters - 1, 1)

    def y(v: float) -> float:
        return TOP + plot_h * (1 - (v - low) / ((high - low) or 1))

    out = _frame(
        title,
        f"{title}. Median and p10 to p90 across paths, {unit}, by quarter after the cutoff of "
        f"{first.result.as_of}. Conditional on the assumed model, not calibrated.",
    )
    for tick in ticks:
        out.append(
            f'<line x1="{LEFT}" x2="{LEFT + plot_w}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{LEFT - 8}" y="{y(tick) + 4:.1f}" font-size="12" text-anchor="end" '
            f'fill="{MUTED}">{tick:,.1f}</text>'
        )
    for i in range(0, quarters, max(1, quarters // 5)):
        out.append(
            f'<text x="{x(i):.1f}" y="{TOP + plot_h + 20}" font-size="12" text-anchor="middle" '
            f'fill="{MUTED}">{escape(labels[i])}</text>'
        )
    out.append(
        f'<text x="{LEFT - 64}" y="{TOP + plot_h / 2:.1f}" font-size="12" fill="{MUTED}" '
        f'transform="rotate(-90 {LEFT - 64} {TOP + plot_h / 2:.1f})" text-anchor="middle">'
        f"{escape(unit)}</text>"
    )
    for _, colour, dash, points in series:
        upper = " ".join(f"{x(i):.1f},{y(p[2]):.1f}" for i, p in enumerate(points))
        lower = " ".join(f"{x(i):.1f},{y(p[0]):.1f}" for i, p in reversed(list(enumerate(points))))
        out.append(f'<polygon points="{upper} {lower}" fill="{colour}" fill-opacity="0.12"/>')
        median = " ".join(f"{x(i):.1f},{y(p[1]):.1f}" for i, p in enumerate(points))
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'<polyline points="{median}" fill="none" stroke="{colour}" stroke-width="2"{dashed}/>'
        )
    ends = sorted(((y(pts[-1][1]), name, colour) for name, colour, _, pts in series))
    last = -100.0
    for position, name, colour in ends:
        position = max(position, last + 16)
        last = position
        out.append(
            f'<text x="{LEFT + plot_w + 8}" y="{position + 4:.1f}" font-size="12" '
            f'fill="{INK}"><tspan fill="{colour}">■</tspan> {escape(name)}</text>'
        )
    out.append(
        f'<text x="{LEFT}" y="{HEIGHT - 12}" font-size="11" fill="{MUTED}">Lines: median. '
        "Bands: p10 to p90 of paths. Conditional on the assumed model, not calibrated.</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def interval_chart(rows: Sequence[tuple[str, float, float, float]], title: str, unit: str) -> str:
    """p10, median and p90 of one quantity for each variant, on one axis with zero marked."""
    plot_w = WIDTH - LEFT - RIGHT - 60
    height = TOP + 48 * len(rows) + 64
    values = [v for _, *trio in rows for v in trio] + [0.0]
    ticks = _ticks(min(values), max(values))
    low, high = min(min(values), ticks[0]), max(max(values), ticks[-1])
    left = LEFT + 120

    def x(v: float) -> float:
        return left + plot_w * (v - low) / ((high - low) or 1)

    out = _frame(
        title,
        f"{title}. Dot: median; whiskers: p10 to p90 of paths, {unit}. Conditional on the "
        "assumed model, not calibrated.",
    )
    out[0] = out[0].replace(f'viewBox="0 0 {WIDTH} {HEIGHT}"', f'viewBox="0 0 {WIDTH} {height}"')
    out[0] = out[0].replace(f'height="{HEIGHT}"', f'height="{height}"')
    out[3] = f'<rect width="{WIDTH}" height="{height}" fill="#ffffff"/>'
    bottom = TOP + 48 * len(rows)
    for tick in ticks:
        out.append(
            f'<line x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="{TOP - 8}" y2="{bottom}" '
            f'stroke="{GRID}"/>'
        )
        out.append(
            f'<text x="{x(tick):.1f}" y="{bottom + 18}" font-size="12" text-anchor="middle" '
            f'fill="{MUTED}">{tick:,.1f}</text>'
        )
    out.append(
        f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{TOP - 8}" y2="{bottom}" stroke="{INK}" '
        'stroke-width="1.5"/>'
    )
    for index, (name, p10, p50, p90) in enumerate(rows):
        row_y = TOP + 48 * index + 20
        colour = VARIANTS[index % 2]
        out.append(
            f'<text x="{left - 12}" y="{row_y + 4}" font-size="13" text-anchor="end" '
            f'fill="{INK}">{escape(name)}</text>'
        )
        out.append(
            f'<line x1="{x(p10):.1f}" x2="{x(p90):.1f}" y1="{row_y}" y2="{row_y}" '
            f'stroke="{colour}" stroke-width="3"/>'
        )
        out.append(f'<circle cx="{x(p50):.1f}" cy="{row_y}" r="6" fill="{colour}"/>')
        out.append(
            f'<text x="{x(p90) + 8:.1f}" y="{row_y + 4}" font-size="12" fill="{MUTED}">'
            f"p50 {p50:,.1f}</text>"
        )
    out.append(
        f'<text x="{left}" y="{height - 14}" font-size="11" fill="{MUTED}">{escape(unit)}. '
        "Dot: median; line: p10 to p90 of paths.</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def ev_change_rows(
    runs: Sequence[tuple[str, SimulationReport]],
) -> list[tuple[str, float, float, float]]:
    rows = []
    for label, report in runs:
        row = next(v for v in report.values if v.metric == "ev_change")
        rows.append(
            (label, _billions(row.p10) or 0.0, _billions(row.p50) or 0.0, _billions(row.p90) or 0.0)
        )
    return rows
