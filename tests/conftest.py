"""Run API/cache tests against temporary evidence, never the user's live cache."""

import shutil
import sqlite3

import pytest

import data_store
from config import DATA_DIR


@pytest.fixture(scope="session")
def test_evidence(tmp_path_factory):
    target = tmp_path_factory.mktemp("evidence") / "data"
    shutil.copytree(DATA_DIR, target)
    return target


@pytest.fixture(autouse=True)
def preserve_air_cache(test_evidence, monkeypatch):
    target = test_evidence / "areas.sqlite"
    monkeypatch.setattr(data_store, "DB", target)
    with sqlite3.connect(target) as db:
        saved = db.execute("SELECT query,fetched_at,payload FROM air_cache").fetchall()
    yield
    with sqlite3.connect(target) as db:
        db.execute("DELETE FROM air_cache")
        db.executemany("INSERT INTO air_cache VALUES (?,?,?)", saved)
