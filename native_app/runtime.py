"""Locate bundled evidence and copy it to a writable app-private directory."""

import json
import os
import shutil
import sqlite3
from pathlib import Path

from config import ROOT


def prepare_runtime(data_directory=None, assets_directory=None):
    # Development and server mode use the existing database and retain its cache.
    bundled = (
        Path(assets_directory or os.environ.get("FLET_ASSETS_DIR", ROOT / "assets")) / "datasets"
    )
    packaged = bool(assets_directory or os.environ.get("FLET_ASSETS_DIR"))
    if not packaged and data_directory is None and (ROOT / "data" / "areas.sqlite").exists():
        return ROOT / "data" / "areas.sqlite"
    private = (
        Path(data_directory or os.environ.get("FLET_APP_STORAGE_DATA", Path.home() / ".localytics"))
        / "evidence"
    )
    private.mkdir(parents=True, exist_ok=True)
    seed = bundled / "areas.sqlite"
    if not seed.exists():
        raise FileNotFoundError(
            "Bundled evidence is missing. Run python scripts/prepare_app.py before building."
        )
    destination = private / "areas.sqlite"
    incoming = json.loads((bundled / "area_manifest.json").read_text())["built_at"]
    current = None
    if destination.exists():
        try:
            with sqlite3.connect(destination) as db:
                current = json.loads(
                    db.execute('SELECT value FROM metadata WHERE key="manifest"').fetchone()[0]
                ).get("built_at")
        except (sqlite3.Error, ValueError, TypeError):
            pass
    if current != incoming:
        temporary = destination.with_suffix(".incoming")
        shutil.copy2(seed, temporary)
        # Preserve the local cache across evidence upgrades; do not ship credentials.
        if destination.exists() and current:
            with sqlite3.connect(destination) as old:
                cached = old.execute("SELECT query,fetched_at,payload FROM air_cache").fetchall()
            with sqlite3.connect(temporary) as fresh:
                fresh.executemany("INSERT OR REPLACE INTO air_cache VALUES (?,?,?)", cached)
        temporary.replace(destination)
    for name in (
        "area_manifest.json",
        "cluster_report.json",
        "evaluation_report.json",
        "boundary_source.md",
    ):
        if (bundled / name).exists():
            shutil.copy2(bundled / name, private / name)
    return destination
