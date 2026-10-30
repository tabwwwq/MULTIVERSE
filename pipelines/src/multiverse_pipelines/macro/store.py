"""The macro vintage store: one SQLite file (standard library), like the PIT warehouse.

``var/data/macro/macro.sqlite`` for archived source files, a separate file for the
synthetic demonstration data, so the two are never mixed. An as-of query returns, for
each period, the value whose availability interval contains the moment.
"""

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from multiverse_contracts.macro import MacroObservation
from multiverse_pipelines.pit.clock import stamp

SCHEMA = """
CREATE TABLE observations (
    series_id TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    available_from TEXT NOT NULL, available_to TEXT, payload TEXT NOT NULL
);
CREATE INDEX observations_as_of ON observations (series_id, available_from);
CREATE TABLE series (series_id TEXT PRIMARY KEY);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class MacroStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection

    @classmethod
    def create(cls, path: Path | None, *, synthetic: bool, built_at: datetime) -> "MacroStore":
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.unlink(missing_ok=True)
        db = sqlite3.connect(":memory:" if path is None else path)
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("synthetic", "yes" if synthetic else "no"), ("built_at", stamp(built_at))],
        )
        db.commit()
        return cls(db)

    @classmethod
    def open(cls, path: Path) -> "MacroStore":
        if not path.exists():
            raise ValueError(
                f"no macro store at {path}: run `python -m multiverse_pipelines.macro build`"
            )
        return cls(sqlite3.connect(path))

    def close(self) -> None:
        self.db.close()

    @property
    def synthetic(self) -> bool:
        row = self.db.execute("SELECT value FROM meta WHERE key = 'synthetic'").fetchone()
        return row is not None and row[0] == "yes"

    def add(self, observations: Iterable[MacroObservation]) -> int:
        rows = [
            (
                o.series_id,
                o.period_start.isoformat(),
                o.period_end.isoformat(),
                stamp(o.available_from),
                stamp(o.available_to) if o.available_to else None,
                o.model_dump_json(),
            )
            for o in observations
        ]
        self.db.executemany("INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)", rows)
        self.db.commit()
        return len(rows)

    def register(self, series_ids: Iterable[str]) -> None:
        """Series whose source files are in the store, even when they hold no value yet."""
        self.db.executemany(
            "INSERT OR IGNORE INTO series VALUES (?)", [(sid,) for sid in series_ids]
        )
        self.db.commit()

    def series(self) -> list[str]:
        rows = self.db.execute(
            "SELECT series_id FROM series UNION SELECT series_id FROM observations ORDER BY 1"
        )
        return [row[0] for row in rows]

    def as_of(self, series_id: str, at: datetime) -> dict[date, MacroObservation]:
        """Each period's value as available at a moment, keyed by period start."""
        rows = self.db.execute(
            "SELECT payload FROM observations WHERE series_id = ? AND available_from <= ?"
            " AND (available_to IS NULL OR available_to > ?) ORDER BY period_start",
            (series_id, stamp(at), stamp(at)),
        )
        found = [MacroObservation.model_validate_json(row[0]) for row in rows]
        return {o.period_start: o for o in found}

    def first_available(
        self, series_id: str, *, until: datetime | None = None
    ) -> dict[date, MacroObservation]:
        """The earliest publication of each period, only among those up to ``until``."""
        limit = stamp(until) if until else "9999"
        rows = self.db.execute(
            "SELECT payload FROM observations WHERE series_id = ? AND available_from <= ?"
            " ORDER BY available_from",
            (series_id, limit),
        )
        found: dict[date, MacroObservation] = {}
        for (payload,) in rows:
            item = MacroObservation.model_validate_json(payload)
            found.setdefault(item.period_start, item)
        return found

    def history(self, series_id: str) -> list[MacroObservation]:
        rows = self.db.execute(
            "SELECT payload FROM observations WHERE series_id = ?"
            " ORDER BY period_start, available_from",
            (series_id,),
        )
        return [MacroObservation.model_validate_json(row[0]) for row in rows]
