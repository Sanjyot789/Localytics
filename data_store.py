"""Shared local evidence storage for the web app and packaged Python clients."""

import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from config import DATA_DIR

DB = DATA_DIR / "areas.sqlite"


class AreaRepository:
    """A repository owns its path: clients never share mutable global file settings."""

    def __init__(self, database):
        self.database = Path(database)
        self._dataset = None

    def dataset(self):
        if self._dataset is None:
            with sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
                manifest = json.loads(
                    db.execute("SELECT value FROM metadata WHERE key=?", ("manifest",)).fetchone()[
                        0
                    ]
                )
                cells = [
                    json.loads(r[0]) for r in db.execute("SELECT payload FROM cells ORDER BY id")
                ]
            self._dataset = cells, manifest
        return self._dataset

    def cache_air(self, state, city, records):
        if not self.database.exists():
            return False
        query = json.dumps([state.casefold(), city.casefold()])
        try:
            with sqlite3.connect(self.database, timeout=15) as db:
                db.execute(
                    "INSERT OR REPLACE INTO air_cache VALUES (?,?,?)",
                    (query, datetime.now(timezone.utc).isoformat(), json.dumps(records)),
                )
            return True
        except (sqlite3.Error, OSError):
            return False

    def query_air(self, state, city):
        if not self.database.exists():
            return [], None
        query = json.dumps([state.casefold(), city.casefold()])
        with sqlite3.connect(self.database) as db:
            row = db.execute(
                "SELECT payload,fetched_at FROM air_cache WHERE query=?", (query,)
            ).fetchone()
        return (json.loads(row[0]), row[1]) if row else ([], None)

    def air_records(self, state="Delhi"):
        if not self.database.exists():
            return [], None
        with sqlite3.connect(self.database) as db:
            rows = db.execute(
                "SELECT query,fetched_at,payload FROM air_cache ORDER BY fetched_at DESC"
            ).fetchall()
        for query, stamp, payload in rows:
            region, city = json.loads(query)
            if region == state.casefold() and not city:
                return json.loads(payload), stamp
        records = []
        seen = set()
        latest = None
        for query, stamp, payload in rows:
            if json.loads(query)[0] != state.casefold():
                continue
            latest = latest or stamp
            for row in json.loads(payload):
                key = (row.get("station"), row.get("pollutant_id"), row.get("last_update"))
                if key not in seen:
                    records.append(row)
                    seen.add(key)
        return records, latest

    def read_report(self, name):
        if Path(name).name != name:
            raise ValueError("Report name must be a filename.")
        try:
            return json.loads(self.database.with_name(name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None


@lru_cache(maxsize=4)
def _repository(path):
    return AreaRepository(path)


def dataset():
    return _repository(DB).dataset()


def cache_air(state, city, records):
    return _repository(DB).cache_air(state, city, records)


def air_records():
    return _repository(DB).air_records()


def read_report(name):
    return _repository(DB).read_report(name)
