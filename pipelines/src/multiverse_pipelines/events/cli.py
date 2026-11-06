"""Commands of the event registry.

python -m multiverse_pipelines.events sample --dataset var/data/forecast/<dataset id>
MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true python -m multiverse_pipelines.events fetch
python -m multiverse_pipelines.events excerpts --stratum item_2_05
python -m multiverse_pipelines.events audit
"""

import argparse
import csv
import json
import sys
import zipfile
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

from multiverse_config import Settings, load_settings
from multiverse_contracts.events import CandidateSample, EventRegistry
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_contracts.sources import DownloadScope
from multiverse_contracts.universe import UniverseManifest
from multiverse_pipelines.events.audit import INDEX_ITEMS, audit, markdown
from multiverse_pipelines.events.candidates import filings_of, sample
from multiverse_pipelines.events.fetch import fetch_documents, stored_path
from multiverse_pipelines.events.reviews import merge_reviews
from multiverse_pipelines.events.text import around, item_section, to_text
from multiverse_pipelines.sec.cli import archive_for, new_run_id, sec_source
from multiverse_pipelines.sec.client import SecClient
from multiverse_pipelines.sec.errors import IngestionError
from multiverse_pipelines.sec.gate import require_permission

UNIVERSE = Path("data/universe/sec-1000-20261030.json")
SAMPLE = Path("data/events/sample.json")
REGISTRY = Path("data/events/registry.json")
SEED = 20261106
SECTIONS = {"item_2_01": "2.01", "item_2_05": "2.05", "item_2_03": "2.03"}
WORDS = {
    "rnd_jump": ("research and development expense", "research and development costs"),
    "capex_jump": ("capital expenditures", "purchases of property"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m multiverse_pipelines.events")
    commands = parser.add_subparsers(dest="command", required=True)
    draw = commands.add_parser("sample", help="draw the filings to read")
    draw.add_argument("--dataset", type=Path, required=True, help="a forecasting dataset folder")
    draw.add_argument("--seed", type=int, default=SEED)
    commands.add_parser("fetch", help="download the documents of the sample (decision D-13)")
    show = commands.add_parser("excerpts", help="print the parts of the documents to read")
    show.add_argument("--stratum")
    show.add_argument("--chars", type=int, default=1500)
    commands.add_parser("audit", help="the quality report of the registry")
    commands.add_parser("index", help="decision items of the filing index, for Stage 20")
    merge = commands.add_parser("reviews", help="add reviews exported from the event screen")
    merge.add_argument("--file", type=Path, required=True)
    return parser


def _sample(args: argparse.Namespace, settings: Settings) -> int:
    universe = UniverseManifest.model_validate_json(UNIVERSE.read_bytes())
    archive = archive_for(settings)
    row = next(
        r
        for r in archive.objects()
        if r.dataset_id == "sec-submissions" and r.path.endswith(".zip")
    )
    drawn = sample(
        universe, archive.root / row.path, args.dataset / "dataset.csv", args.seed, date.today()
    )
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(
        json.dumps(drawn.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{drawn.sample_id}: {len(drawn.candidates)} filings")
    for stratum, count in drawn.drawn.items():
        print(f"{stratum}: {count} of {drawn.population[stratum]}")
    return 0


def _fetch(settings: Settings, transport: httpx.BaseTransport | None) -> int:
    source = sec_source()
    user_agent = require_permission(settings, source, DownloadScope.SAMPLE)
    archive = archive_for(settings)
    drawn = CandidateSample.model_validate_json(SAMPLE.read_bytes())
    with SecClient(
        user_agent=user_agent,
        allowed_hosts=source.official_hosts,
        rate_per_second=Decimal(source.rate_limit.chosen_requests_per_second),
        tmp_dir=archive.tmp_dir,
        transport=transport,
    ) as client:
        manifest = fetch_documents(
            client, archive, source, drawn, SOURCE_CATALOG.contracts_version, new_run_id()
        )
    archive.save_manifest(manifest)
    failed = [r for r in manifest.records if r.error]
    print(f"{manifest.status}: {len(manifest.records)} documents, {len(failed)} failed")
    for record in failed:
        print(f"failed {record.key}: {record.error}")
    return 0


def _excerpts(args: argparse.Namespace, settings: Settings) -> int:
    archive = archive_for(settings)
    drawn = CandidateSample.model_validate_json(SAMPLE.read_bytes())
    for candidate in drawn.candidates:
        if args.stratum and candidate.stratum != args.stratum:
            continue
        path = stored_path(archive, candidate)
        print(f"\n=== {candidate.candidate_id} | {candidate.company} | {candidate.filed_at}")
        if path is None:
            print("(not stored)")
            continue
        text = to_text(path.read_text(encoding="utf-8", errors="replace"))
        item = SECTIONS.get(candidate.stratum)
        if item is not None:
            print((item_section(text, item) or text)[: args.chars])
        else:
            for passage in around(text, WORDS[candidate.stratum]):
                print("...", passage)
    return 0


def _audit(settings: Settings) -> int:
    drawn = CandidateSample.model_validate_json(SAMPLE.read_bytes())
    registry = EventRegistry.model_validate_json(REGISTRY.read_bytes())
    archive = archive_for(settings)
    row = next(
        r
        for r in archive.objects()
        if r.dataset_id == "sec-submissions" and r.path.endswith(".zip")
    )
    with zipfile.ZipFile(archive.root / row.path) as bulk:
        filings = filings_of(bulk, sorted({e.cik for e in registry.events}))
    report = audit(registry, drawn, filings)
    folder = settings.data_dir / "events"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "quality.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    text = markdown(report)
    (folder / "quality.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def _index(settings: Settings) -> int:
    """Every 8-K decision item of the universe: what the causal package may read of it."""
    universe = UniverseManifest.model_validate_json(UNIVERSE.read_bytes())
    archive = archive_for(settings)
    row = next(
        r
        for r in archive.objects()
        if r.dataset_id == "sec-submissions" and r.path.endswith(".zip")
    )
    with zipfile.ZipFile(archive.root / row.path) as bulk:
        filings = filings_of(bulk, [c.cik for c in universe.companies])
    folder = settings.data_dir / "events"
    folder.mkdir(parents=True, exist_ok=True)
    count = 0
    with (folder / "decisions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("cik", "filed_on", "item"))
        for cik, rows in sorted(filings.items()):
            for filing in rows:
                for item in filing.items:
                    if filing.form == "8-K" and item in INDEX_ITEMS:
                        writer.writerow((cik, filing.filed_on.isoformat(), item))
                        count += 1
    print(f"{count} decision items")
    return 0


def _reviews(args: argparse.Namespace) -> int:
    registry = EventRegistry.model_validate_json(REGISTRY.read_bytes())
    rows = json.loads(args.file.read_text(encoding="utf-8"))
    merged = merge_reviews(registry, rows)
    REGISTRY.write_text(
        json.dumps(merged.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} reviews added")
    return 0


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings()
    try:
        if args.command == "sample":
            return _sample(args, settings)
        if args.command == "fetch":
            return _fetch(settings, transport)
        if args.command == "excerpts":
            return _excerpts(args, settings)
        if args.command == "reviews":
            return _reviews(args)
        if args.command == "index":
            return _index(settings)
        return _audit(settings)
    except (OSError, ValueError, IngestionError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
