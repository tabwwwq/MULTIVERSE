"""Structural checks of SEC files before they enter the archive.

A file is kept only if it parses and has the shape its dataset promises: the columns
of the submissions filing table have equal lengths, every company fact names its
filing and filing date, a ZIP passes its CRC check and holds the expected members.
The checks also read the filing count and the latest filing for the metadata index.
"""

import json
import zipfile
import zlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from multiverse_pipelines.sec.cik import cik10, cik_int
from multiverse_pipelines.sec.errors import InvalidPayloadError

FILING_COLUMNS = ("accessionNumber", "filingDate", "acceptanceDateTime", "form")
FACT_FIELDS = ("accn", "filed", "end", "val", "form")
FSDS_MEMBERS = ("sub.txt", "num.txt", "tag.txt", "pre.txt")


@dataclass(frozen=True)
class Summary:
    filing_count: int | None = None
    latest_filing_id: str | None = None
    latest_filed: date | None = None
    pages: tuple[str, ...] = ()


def load_json(path: Path) -> Any:
    try:
        with path.open("rb") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidPayloadError(f"{path.name} is not valid JSON: {exc}") from exc


def _object(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidPayloadError(f"{where} must be an object")
    return value


def _day(value: Any, where: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise InvalidPayloadError(f"{where} is not a date: {value!r}") from exc


def _same_cik(found: Any, expected: str, where: str) -> None:
    try:
        same = cik_int(found) == cik_int(expected)
    except ValueError:
        same = False
    if not same:
        raise InvalidPayloadError(f"{where} holds CIK {found!r}, expected {cik10(expected)}")


def _filing_table(table: Mapping[str, Any], where: str) -> Summary:
    columns = [table.get(name) for name in FILING_COLUMNS]
    if not all(isinstance(column, list) for column in columns):
        raise InvalidPayloadError(f"{where} lacks one of the columns {', '.join(FILING_COLUMNS)}")
    lengths = {len(column) for column in columns if isinstance(column, list)}
    if len(lengths) != 1:
        raise InvalidPayloadError(f"{where} columns have different lengths: {sorted(lengths)}")
    accessions, filed = table["accessionNumber"], table["filingDate"]
    if not accessions:
        return Summary(filing_count=0)
    days = [_day(value, f"{where}.filingDate") for value in filed]
    latest = max(range(len(days)), key=lambda i: (days[i], str(accessions[i])))
    return Summary(len(accessions), str(accessions[latest]), days[latest])


def check_submissions(path: Path, cik: str) -> Summary:
    """CIK##########.json: company metadata, the latest filings and pages of older ones."""
    doc = _object(load_json(path), "submissions")
    _same_cik(doc.get("cik"), cik, "submissions")
    if not isinstance(doc.get("name"), str):
        raise InvalidPayloadError("submissions lacks the company name")
    filings = _object(doc.get("filings"), "submissions.filings")
    recent = _filing_table(_object(filings.get("recent"), "filings.recent"), "filings.recent")
    files = filings.get("files", [])
    if not isinstance(files, list):
        raise InvalidPayloadError("filings.files must be a list")
    pages: list[str] = []
    older = 0
    for item in files:
        page = _object(item, "filings.files[]")
        name, count = page.get("name"), page.get("filingCount")
        if not isinstance(name, str) or not isinstance(count, int):
            raise InvalidPayloadError("each older-filing page needs a name and a filingCount")
        pages.append(name)
        older += count
    return Summary(
        filing_count=(recent.filing_count or 0) + older,
        latest_filing_id=recent.latest_filing_id,
        latest_filed=recent.latest_filed,
        pages=tuple(pages),
    )


def check_submissions_page(path: Path) -> Summary:
    """CIK##########-submissions-001.json: the same filing columns, for older filings."""
    return _filing_table(_object(load_json(path), "submissions page"), "submissions page")


def check_companyfacts(path: Path, cik: str) -> Summary:
    """CIK##########.json of the XBRL API: every fact with its filing and filing date."""
    doc = _object(load_json(path), "companyfacts")
    _same_cik(doc.get("cik"), cik, "companyfacts")
    if not isinstance(doc.get("entityName"), str):
        raise InvalidPayloadError("companyfacts lacks entityName")
    facts = _object(doc.get("facts"), "companyfacts.facts")
    accessions: set[str] = set()
    latest: tuple[date, str] | None = None
    for taxonomy, concepts in facts.items():
        for tag, concept in _object(concepts, f"facts.{taxonomy}").items():
            units = _object(_object(concept, f"{taxonomy}:{tag}").get("units"), f"{tag}.units")
            for unit, values in units.items():
                if not isinstance(values, list):
                    raise InvalidPayloadError(f"{taxonomy}:{tag} [{unit}] must be a list")
                for value in values:
                    entry = _object(value, f"{taxonomy}:{tag} value")
                    missing = [name for name in FACT_FIELDS if name not in entry]
                    if missing:
                        raise InvalidPayloadError(
                            f"{taxonomy}:{tag} value lacks {', '.join(missing)}"
                        )
                    accession = str(entry["accn"])
                    accessions.add(accession)
                    filed = _day(entry["filed"], f"{taxonomy}:{tag}.filed")
                    if latest is None or (filed, accession) > latest:
                        latest = (filed, accession)
    if latest is None:
        return Summary(filing_count=0)
    return Summary(len(accessions), latest[1], latest[0])


def check_zip(path: Path, required: Collection[str] = ()) -> Summary:
    """A ZIP whose every member passes its CRC check, with the members a dataset needs."""
    try:
        with zipfile.ZipFile(path) as archive:
            broken = archive.testzip()
            names = set(archive.namelist())
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError) as exc:
        raise InvalidPayloadError(f"{path.name} is not a readable ZIP: {exc}") from exc
    if broken is not None:
        raise InvalidPayloadError(f"{path.name}: CRC check failed for {broken}")
    missing = sorted(set(required) - names)
    if missing:
        raise InvalidPayloadError(f"{path.name} lacks {', '.join(missing)}")
    return Summary()
