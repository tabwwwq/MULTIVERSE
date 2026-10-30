"""The point-in-time warehouse: one SQLite file (standard library, no server).

Tables (``var/data/pit/warehouse.sqlite`` by default, never committed):

    pit_values   every normalized value with its interval of knowledge time
    filings      the filing index: form, dates, acceptance, when public
    attributes   names over time; current ticker, exchange, SIC with when observed
    alerts       broken chronology alerts
    inputs       the raw archive files each company was built from (path, SHA-256)
    meta         policy, contracts version, build time
    codec        the zlib dictionary of the payloads

Knowledge times are stored as fixed-width UTC text, so text order is time order. An
as-of query is one indexed range condition: ``known_from <= cutoff < known_to``.

A value's payload is its JSON, compressed with zlib primed by a dictionary: payload text
of the first company built. Rows share most of their text (field names, concepts, enum
values), so a primed row is about seven times smaller than its JSON, against twice for
zlib alone; that keeps a 1000-company warehouse near a gigabyte.
"""

import sqlite3
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from multiverse_contracts.normalized import FiscalPeriod, Revision
from multiverse_contracts.pit import (
    PIT_POLICY_VERSION,
    ChronologyAlert,
    EntityAttribute,
    KnowledgeView,
    PitValue,
    SnapshotInput,
    TimePrecision,
    ValueChange,
)
from multiverse_contracts.version import CONTRACTS_VERSION
from multiverse_pipelines.pit.clock import eastern_date, from_stamp, stamp
from multiverse_pipelines.pit.filings import Filing, FilingIndex
from multiverse_pipelines.pit.vintages import CompanyHistory
from multiverse_pipelines.sec.cik import cik10

SCHEMA = """
CREATE TABLE pit_values (
    cik TEXT NOT NULL, metric TEXT NOT NULL, fiscal_year INTEGER NOT NULL,
    fiscal_period TEXT NOT NULL, revision TEXT NOT NULL, period_end TEXT NOT NULL,
    known_from TEXT NOT NULL, known_to TEXT, has_value INTEGER NOT NULL, change TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE INDEX pit_values_as_of ON pit_values (cik, revision, metric, known_from);
CREATE TABLE filings (
    cik TEXT NOT NULL, accession TEXT NOT NULL, form TEXT NOT NULL, filing_date TEXT NOT NULL,
    report_date TEXT, accepted TEXT, known_at TEXT NOT NULL, precision TEXT NOT NULL,
    xbrl INTEGER NOT NULL, PRIMARY KEY (cik, accession)
);
CREATE TABLE attributes (cik TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE alerts (cik TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE inputs (cik TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE companies (
    cik TEXT PRIMARY KEY, knowledge_points INTEGER NOT NULL, estimates_dropped INTEGER NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE codec (dictionary BLOB NOT NULL);
"""
DICTIONARY_BYTES = 32 * 1024
DICTIONARY_SAMPLES = 40
Row = tuple[object, ...]


def make_dictionary(values: Sequence[PitValue]) -> bytes:
    """Payload text spread over one company's values: what zlib is primed with."""
    step = max(1, len(values) // DICTIONARY_SAMPLES)
    text = b"".join(v.model_dump_json().encode() for v in values[::step])
    return text[-DICTIONARY_BYTES:]


def encode(value: PitValue, dictionary: bytes) -> bytes:
    packer = zlib.compressobj(6, zdict=dictionary) if dictionary else zlib.compressobj(6)
    return packer.compress(value.model_dump_json().encode()) + packer.flush()


def decode(payload: bytes, dictionary: bytes) -> PitValue:
    unpacker = zlib.decompressobj(zdict=dictionary) if dictionary else zlib.decompressobj()
    return PitValue.model_validate_json(unpacker.decompress(payload) + unpacker.flush())


@dataclass(frozen=True)
class CompanyRows:
    """One company's rows, ready to insert: encoded in a worker, inserted by the parent."""

    cik: str
    values: list[Row]
    filings: list[Row]
    documents: dict[str, list[str]]
    knowledge_points: int
    estimates_dropped: int


def company_rows(
    history: CompanyHistory,
    filings: Sequence[Filing],
    attributes: Sequence[EntityAttribute],
    alerts: Sequence[ChronologyAlert],
    inputs: Sequence[SnapshotInput],
    dictionary: bytes,
) -> CompanyRows:
    cik = history.cik
    values: list[Row] = [
        (
            cik,
            v.value.metric,
            v.value.fiscal_year,
            v.value.fiscal_period.value,
            v.value.revision.value,
            v.value.period_end.isoformat(),
            stamp(v.known_from),
            stamp(v.known_to) if v.known_to else None,
            int(v.value.value is not None),
            v.change.value,
            encode(v, dictionary),
        )
        for v in history.values
    ]
    rows: list[Row] = [
        (
            cik,
            f.accession,
            f.form,
            f.filing_date.isoformat(),
            f.report_date.isoformat() if f.report_date else None,
            stamp(f.accepted) if f.accepted else None,
            stamp(f.known_at),
            f.precision.value,
            int(f.xbrl),
        )
        for f in filings
    ]
    documents = {
        table: [item.model_dump_json() for item in items]
        for table, items in (("attributes", attributes), ("alerts", alerts), ("inputs", inputs))
    }
    return CompanyRows(
        cik, values, rows, documents, history.knowledge_points, history.estimates_dropped
    )


class Warehouse:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection
        row = connection.execute("SELECT dictionary FROM codec").fetchone()
        self.dictionary: bytes = row[0] if row else b""
        self._filings: dict[str, FilingIndex] = {}

    @classmethod
    def create(
        cls, path: Path | None = None, *, built_at: datetime, dictionary: bytes = b""
    ) -> "Warehouse":
        """A new, empty warehouse; an existing file at the path is replaced."""
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.unlink(missing_ok=True)
        db = sqlite3.connect(":memory:" if path is None else path)
        db.executescript(SCHEMA)
        meta = {
            "policy_version": PIT_POLICY_VERSION,
            "contracts_version": CONTRACTS_VERSION,
            "built_at": stamp(built_at),
        }
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        db.execute("INSERT INTO codec VALUES (?)", (dictionary,))
        db.commit()
        return cls(db)

    @classmethod
    def open(cls, path: Path) -> "Warehouse":
        if not path.exists():
            raise ValueError(
                f"no warehouse at {path}: run `python -m multiverse_pipelines.pit build`"
            )
        db = sqlite3.connect(path)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'codec'").fetchone():
            db.close()
            raise ValueError(f"{path} was built by an earlier version: rebuild the warehouse")
        return cls(db)

    def close(self) -> None:
        self.db.close()

    def meta(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT key, value FROM meta").fetchall())

    def add_company(
        self,
        history: CompanyHistory,
        filings: Sequence[Filing],
        attributes: Sequence[EntityAttribute],
        alerts: Sequence[ChronologyAlert],
        inputs: Sequence[SnapshotInput],
    ) -> None:
        self.insert(company_rows(history, filings, attributes, alerts, inputs, self.dictionary))

    def insert(self, rows: CompanyRows) -> None:
        """One company, encoded with this warehouse's dictionary, in one transaction."""
        self.db.executemany(
            "INSERT INTO pit_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows.values
        )
        self.db.executemany("INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows.filings)
        for table, payloads in rows.documents.items():
            self.db.executemany(
                f"INSERT INTO {table} VALUES (?, ?)", ((rows.cik, p) for p in payloads)
            )
        self.db.execute(
            "INSERT INTO companies VALUES (?, ?, ?)",
            (rows.cik, rows.knowledge_points, rows.estimates_dropped),
        )
        self.db.commit()

    def _values(self, sql: str, args: Sequence[object]) -> list[PitValue]:
        return [decode(row[0], self.dictionary) for row in self.db.execute(sql, args)]

    def ciks(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT cik FROM companies ORDER BY cik")]

    def as_of(
        self,
        cik: str,
        at: datetime,
        *,
        view: KnowledgeView = KnowledgeView.VINTAGE,
        metric: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: FiscalPeriod | None = None,
    ) -> list[PitValue]:
        """Values of one company as known at a moment, in one knowledge view.

        Only periods ended by the moment's date are returned. ``latest`` ignores the
        moment and returns what was known when the warehouse was built: hindsight, for
        studying revisions only.
        """
        revision = Revision.ORIGINAL if view is KnowledgeView.ORIGINAL else Revision.LATEST
        sql = "SELECT payload FROM pit_values WHERE cik = ? AND revision = ?"
        args: list[object] = [cik10(cik), revision.value]
        if view is KnowledgeView.LATEST:
            sql += " AND known_to IS NULL AND period_end <= ?"
            args.append(eastern_date(from_stamp(self.meta()["built_at"])).isoformat())
        else:
            sql += " AND known_from <= ? AND (known_to IS NULL OR known_to > ?) AND period_end <= ?"
            args += [stamp(at), stamp(at), eastern_date(at).isoformat()]
        if metric is not None:
            sql += " AND metric = ?"
            args.append(metric)
        if fiscal_year is not None:
            sql += " AND fiscal_year = ?"
            args.append(fiscal_year)
        if fiscal_period is not None:
            sql += " AND fiscal_period = ?"
            args.append(fiscal_period.value)
        sql += " ORDER BY metric, period_end, fiscal_period"
        return self._values(sql, args)

    def history(
        self,
        cik: str,
        metric: str,
        fiscal_year: int,
        fiscal_period: FiscalPeriod,
        revision: Revision = Revision.LATEST,
    ) -> list[PitValue]:
        """Every answer one period had, oldest first: its corrections over time."""
        return self._values(
            "SELECT payload FROM pit_values WHERE cik = ? AND metric = ? AND fiscal_year = ?"
            " AND fiscal_period = ? AND revision = ? ORDER BY known_from",
            (cik10(cik), metric, fiscal_year, fiscal_period.value, revision.value),
        )

    def all_values(self, cik: str) -> list[PitValue]:
        return self._values(
            "SELECT payload FROM pit_values WHERE cik = ? ORDER BY rowid", (cik10(cik),)
        )

    def current(self, cik: str) -> list[PitValue]:
        """Latest-revision values as known at the build: the answer of today."""
        return self._values(
            "SELECT payload FROM pit_values WHERE cik = ? AND revision = ? AND known_to IS NULL"
            " ORDER BY rowid",
            (cik10(cik), Revision.LATEST.value),
        )

    def revised(self, cik: str) -> dict[str, int]:
        """Per metric: latest-revision values that replaced an earlier, different answer."""
        rows = self.db.execute(
            "SELECT metric, COUNT(*) FROM pit_values WHERE cik = ? AND revision = ?"
            " AND change = ? GROUP BY metric",
            (cik10(cik), Revision.LATEST.value, ValueChange.VALUE_REVISED.value),
        )
        return dict(rows.fetchall())

    def filings(self, cik: str) -> FilingIndex:
        """The filing index of one company (read once, then kept)."""
        cik = cik10(cik)
        if cik not in self._filings:
            self._filings[cik] = self._read_filings(cik)
        return self._filings[cik]

    def _read_filings(self, cik: str) -> FilingIndex:
        rows = self.db.execute(
            "SELECT accession, form, filing_date, report_date, accepted, known_at, precision,"
            " xbrl FROM filings WHERE cik = ?",
            (cik,),
        )
        return FilingIndex(
            Filing(
                accession=accession,
                form=form,
                filing_date=date.fromisoformat(filing_date),
                report_date=date.fromisoformat(report_date) if report_date else None,
                accepted=from_stamp(accepted) if accepted else None,
                known_at=from_stamp(known_at),
                precision=TimePrecision(precision),
                xbrl=bool(xbrl),
            )
            for (
                accession,
                form,
                filing_date,
                report_date,
                accepted,
                known_at,
                precision,
                xbrl,
            ) in rows
        )

    def attributes(self, ciks: Iterable[str] | None = None) -> list[EntityAttribute]:
        return [EntityAttribute.model_validate_json(p) for p in self._payloads("attributes", ciks)]

    def alerts(self, ciks: Iterable[str] | None = None) -> list[ChronologyAlert]:
        return [ChronologyAlert.model_validate_json(p) for p in self._payloads("alerts", ciks)]

    def inputs(self, ciks: Iterable[str] | None = None) -> list[SnapshotInput]:
        found = [SnapshotInput.model_validate_json(p) for p in self._payloads("inputs", ciks)]
        return sorted(found, key=lambda item: item.path)

    def counts(self) -> dict[str, tuple[int, int, int]]:
        """Per company: knowledge points, value intervals, estimates left out."""
        found: dict[str, tuple[int, int, int]] = {}
        for cik, points, estimates in self.db.execute("SELECT * FROM companies ORDER BY cik"):
            (intervals,) = self.db.execute(
                "SELECT COUNT(*) FROM pit_values WHERE cik = ?", (cik,)
            ).fetchone()
            found[cik] = (points, intervals, estimates)
        return found

    def _payloads(self, table: str, ciks: Iterable[str] | None) -> list[str]:
        rows = self.db.execute(f"SELECT cik, payload FROM {table} ORDER BY rowid")
        wanted = None if ciks is None else {cik10(c) for c in ciks}
        return [payload for cik, payload in rows if wanted is None or cik in wanted]
