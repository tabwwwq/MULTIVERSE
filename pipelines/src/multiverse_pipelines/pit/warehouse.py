"""The point-in-time warehouse: one SQLite file (standard library, no server).

Tables (``var/data/pit/warehouse.sqlite`` by default, never committed):

    pit_values   every normalized value with its interval of knowledge time
    filings      the filing index: form, dates, acceptance, when public
    attributes   names over time; current ticker, exchange, SIC with when observed
    alerts       broken chronology alerts
    inputs       the raw archive files each company was built from (path, SHA-256)
    meta         policy, contracts version, build time

Knowledge times are stored as fixed-width UTC text, so text order is time order. An
as-of query is one indexed range condition: ``known_from <= cutoff < known_to``.
"""

import sqlite3
from collections.abc import Iterable, Sequence
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
    known_from TEXT NOT NULL, known_to TEXT, has_value INTEGER NOT NULL, payload TEXT NOT NULL
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
"""


class Warehouse:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection

    @classmethod
    def create(cls, path: Path | None = None, *, built_at: datetime) -> "Warehouse":
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
        db.commit()
        return cls(db)

    @classmethod
    def open(cls, path: Path) -> "Warehouse":
        if not path.exists():
            raise ValueError(
                f"no warehouse at {path}: run `python -m multiverse_pipelines.pit build`"
            )
        return cls(sqlite3.connect(path))

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
        cik = history.cik
        self.db.executemany(
            "INSERT INTO pit_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
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
                    v.model_dump_json(),
                )
                for v in history.values
            ),
        )
        self.db.executemany(
            "INSERT INTO filings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
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
            ),
        )
        for table, items in (("attributes", attributes), ("alerts", alerts), ("inputs", inputs)):
            self.db.executemany(
                f"INSERT INTO {table} VALUES (?, ?)",
                ((cik, item.model_dump_json()) for item in items),
            )
        self.db.execute(
            "INSERT INTO companies VALUES (?, ?, ?)",
            (cik, history.knowledge_points, history.estimates_dropped),
        )
        self.db.commit()

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
        return [PitValue.model_validate_json(row[0]) for row in self.db.execute(sql, args)]

    def history(
        self,
        cik: str,
        metric: str,
        fiscal_year: int,
        fiscal_period: FiscalPeriod,
        revision: Revision = Revision.LATEST,
    ) -> list[PitValue]:
        """Every answer one period had, oldest first: its corrections over time."""
        rows = self.db.execute(
            "SELECT payload FROM pit_values WHERE cik = ? AND metric = ? AND fiscal_year = ?"
            " AND fiscal_period = ? AND revision = ? ORDER BY known_from",
            (cik10(cik), metric, fiscal_year, fiscal_period.value, revision.value),
        )
        return [PitValue.model_validate_json(row[0]) for row in rows]

    def all_values(self, cik: str) -> list[PitValue]:
        rows = self.db.execute(
            "SELECT payload FROM pit_values WHERE cik = ? ORDER BY rowid", (cik10(cik),)
        )
        return [PitValue.model_validate_json(row[0]) for row in rows]

    def filings(self, cik: str) -> FilingIndex:
        rows = self.db.execute(
            "SELECT accession, form, filing_date, report_date, accepted, known_at, precision,"
            " xbrl FROM filings WHERE cik = ?",
            (cik10(cik),),
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
