"""Bundle public evidence for native builds without API keys or cached query history."""

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(root=ROOT):
    source = root / "data"
    target = root / "assets" / "datasets"
    if not (source / "areas.sqlite").exists():
        raise FileNotFoundError("Build data/areas.sqlite with scripts/build_areas.py first.")
    target.mkdir(parents=True, exist_ok=True)
    database = target / "areas.sqlite"
    with (
        sqlite3.connect((source / "areas.sqlite").resolve().as_uri() + "?mode=ro", uri=True) as src,
        sqlite3.connect(database) as dst,
    ):
        src.backup(dst)
        dst.execute("DELETE FROM air_cache")
        dst.commit()
        dst.execute("VACUUM")
    for name in (
        "area_manifest.json",
        "cluster_report.json",
        "evaluation_report.json",
        "boundary_source.md",
    ):
        if (source / name).exists():
            shutil.copy2(source / name, target / name)
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.iterdir()
        if p.is_file() and p.name != "bundle_manifest.json"
    }
    (target / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Prepared bundled evidence. No .env, API keys or cached queries were copied.")
    return target


if __name__ == "__main__":
    prepare()
