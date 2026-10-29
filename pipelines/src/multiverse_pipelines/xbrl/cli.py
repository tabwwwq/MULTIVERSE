"""Commands of XBRL normalization: ``python -m multiverse_pipelines.xbrl <command>``.

Both commands read only the local raw archive of Stage 10; neither touches the network.

    normalize   all archived candidates (or --cik) into var/data/normalized/sec
    show        one company and fiscal year as a table, for reconciliation with filings
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from multiverse_config import load_settings
from multiverse_contracts.normalized import FiscalPeriod, NormalizedValue, Revision
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.cik import cik10
from multiverse_pipelines.sec.ingest import COMPANYFACTS
from multiverse_pipelines.sec.validate import load_json
from multiverse_pipelines.xbrl.concepts import CALCULATED, METRICS
from multiverse_pipelines.xbrl.facts import facts_from_companyfacts
from multiverse_pipelines.xbrl.normalize import CompanyNormalizer
from multiverse_pipelines.xbrl.tables import write_outputs

METHOD_CODES = {
    "reported": "R",
    "ytd_to_quarter": "YTD",
    "fy_minus_nine_months": "FY-9M",
    "fy_minus_three_quarters": "FY-3Q",
    "calculated": "CALC",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m multiverse_pipelines.xbrl",
        description="Canonical financial values from archived SEC company facts (Stage 11).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    normalize = commands.add_parser("normalize", help="write the standardized tables")
    normalize.add_argument("--cik", action="append", help="repeatable; default: catalog candidates")
    normalize.add_argument("--out", type=Path, help="default: <data dir>/normalized/sec")
    show = commands.add_parser("show", help="one company and fiscal year, for reconciliation")
    show.add_argument("--cik", required=True)
    show.add_argument("--fiscal-year", type=int, required=True)
    show.add_argument("--revision", choices=[r.value for r in Revision], default="latest")
    return parser


def load_company(archive: RawArchive, cik: str) -> tuple[CompanyNormalizer, str, str]:
    row = archive.latest(COMPANYFACTS, f"CIK{cik10(cik)}")
    if row is None:
        raise ValueError(f"no archived company facts for CIK {cik10(cik)}; run the SEC sample")
    doc = load_json(archive.root / row.path)
    return CompanyNormalizer(cik, facts_from_companyfacts(doc)), row.path, row.sha256


def _millions(row: NormalizedValue) -> str:
    if row.value is None:
        return "-"
    number = float(row.value)
    text = f"{number / 1e6:,.1f}" if row.unit != "shares" or abs(number) >= 1e5 else row.value
    return f"{text} {METHOD_CODES.get(row.method.value if row.method else '', '')}".strip()


def show(rows: Sequence[NormalizedValue], fiscal_year: int, revision: Revision) -> str:
    periods = list(FiscalPeriod)
    lines = ["| metric | " + " | ".join(p.value for p in periods) + " |", "|---|" + "---|" * 5]
    names = [spec.metric for spec in METRICS] + [spec.metric for spec in CALCULATED]
    index = {
        (r.metric, r.fiscal_period): r
        for r in rows
        if r.fiscal_year == fiscal_year and r.revision is revision
    }
    for name in names:
        cells = [index.get((name, p)) for p in periods]
        lines.append(f"| {name} | " + " | ".join(_millions(c) if c else "" for c in cells) + " |")
    lines.append("")
    lines.append("Millions (shares in millions); R reported, YTD year-to-date difference, ")
    lines.append("FY-9M fiscal year minus nine months, CALC calculated, - missing.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    archive = RawArchive(settings.raw_dir, budget_bytes=settings.raw_budget_mb * 1024 * 1024)
    names = {c.cik: c.name for c in SOURCE_CATALOG.candidates}
    try:
        if args.command == "show":
            normalizer, _, _ = load_company(archive, args.cik)
            print(show(normalizer.normalize(), args.fiscal_year, Revision(args.revision)), end="")
            return 0
        ciks = [cik10(c) for c in (args.cik or [c.cik for c in SOURCE_CATALOG.candidates])]
        rows: list[NormalizedValue] = []
        inputs: list[dict[str, object]] = []
        for cik in ciks:
            normalizer, path, sha = load_company(archive, cik)
            company = normalizer.normalize()
            rows += company
            values = sum(r.value is not None for r in company)
            print(
                f"{cik} {names.get(cik, ''):<34} {len(normalizer.calendar.years):>2} years "
                f"{values:>6} values {len(company) - values:>6} missing "
                f"{normalizer.duplicates} duplicates dropped, {normalizer.ambiguous} ambiguous"
            )
            inputs.append(
                {
                    "cik": cik,
                    "path": path,
                    "sha256": sha,
                    "currency": normalizer.currency,
                    "duplicates_dropped": normalizer.duplicates,
                    "facts_outside_fiscal_slots": normalizer.unplaced,
                }
            )
        folder = args.out or settings.data_dir / "normalized" / "sec"
        counts = write_outputs(rows, folder, inputs=inputs, names=names)
        print(f"wrote {folder}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        return 0
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
