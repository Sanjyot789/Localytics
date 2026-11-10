"""UI-independent operations shared by browser, phone and desktop sessions."""

import csv
import io
import json
import sqlite3
from dataclasses import dataclass, field

import areas
from air_client import PythonAirClient
from config import DEFAULTS, FACTORS
from data_store import AreaRepository
from geography import coordinates, covered_radius, distance_km
from observations import monitors
from preferences import preferences


@dataclass
class Selection:
    weights: dict = field(default_factory=lambda: dict(DEFAULTS))
    radius: int = 2
    cap: int = 10
    workplace: tuple | None = None
    must: dict = field(default_factory=dict)

    def validate(self):
        values = {f"w_{k}": self.weights.get(k, 0) for k in FACTORS}
        values.update(radius=self.radius, cap=self.cap)
        if self.workplace:
            values.update(work_lat=str(self.workplace[0]), work_lon=str(self.workplace[1]))
        values.update({f"must_{k}": str(v) for k, v in self.must.items()})
        return Selection(*preferences(values))


def _inside_ring(lat, lon, ring):
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        x1, y1 = a
        x2, y2 = b
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(geometry, lat, lon):
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    return any(
        _inside_ring(lat, lon, p[0]) and not any(_inside_ring(lat, lon, h) for h in p[1:])
        for p in polygons
    )


def score_color(score):
    return (
        "#A8AFB7"
        if score is None
        else "#16834A"
        if score >= 70
        else "#E9A522"
        if score >= 40
        else "#CC4949"
    )


class LocalyticsService:
    def __init__(self, database):
        self.repository = AreaRepository(database)
        self.cells, self.manifest = self.repository.dataset()
        self.cells_by_id = {c["id"]: c for c in self.cells}
        self.selection = Selection()
        self.results = []
        self.by_id = {}
        self.comparison = []
        self.reload_air()
        self.apply(self.selection)

    def reload_air(self):
        self.air_rows, self.air_fetched = self.repository.air_records()
        self.stations = monitors(self.air_rows)

    def apply(self, selection):
        chosen = selection.validate()
        results = areas.rank(
            self.cells,
            chosen.weights,
            chosen.radius,
            chosen.cap,
            self.stations,
            chosen.workplace,
            chosen.must,
        )
        self.selection = chosen
        self.results = results
        self.by_id = {r["id"]: r for r in results}
        self.comparison = [id for id in self.comparison if id in self.by_id]
        return self.shortlist

    @property
    def shortlist(self):
        return [r for r in self.results if r["score"] is not None][:10]

    def select_at(self, latitude, longitude):
        lat, lon = coordinates(latitude, longitude)
        return next(
            (self.by_id[c["id"]] for c in self.cells if contains(c["geometry"], lat, lon)), None
        )

    def compare(self, cell_id):
        if cell_id not in self.by_id:
            raise ValueError("Unknown area.")
        if cell_id in self.comparison:
            self.comparison.remove(cell_id)
        elif len(self.comparison) >= 3:
            raise ValueError("Compare up to three areas. Remove one first.")
        else:
            self.comparison.append(cell_id)
        return [self.by_id[id] for id in self.comparison]

    def clusters(self):
        report = self.repository.read_report("cluster_report.json")
        if not isinstance(report, dict) or report.get("data_version") != self.manifest["built_at"]:
            return dict(
                available=False,
                labels={},
                reason="Rebuild the clustering report on your analysis computer.",
            )
        return report

    def refresh(self, state, city="", api_key=None):
        rows = PythonAirClient(api_key).fetch_records(state, city)
        self.repository.cache_air(state, city, rows)
        if state.strip().casefold() == "delhi":
            self.reload_air()
            self.apply(self.selection)
        return rows

    def nearby_transport(self, lat, lon, radius=5, limit=5):
        lat, lon = coordinates(lat, lon)
        if not 0.1 <= radius <= 100 or not 1 <= limit <= 20:
            raise ValueError("Radius must be 0.1-100 km; results per type 1-20.")
        sources = self.manifest["sources"]
        bounds = [b for source in sources for b in source["bounds"]]

        covered = covered_radius(lat, lon, radius, bounds)
        with sqlite3.connect(self.repository.database) as db:
            records = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM facilities WHERE category IN ('bus_stop','metro_station','airport_terminal')"
                )
            ]
        result = {k: [] for k in ("bus_stop", "metro_station", "airport_terminal")}
        for p in records:
            d = distance_km(lat, lon, p["lat"], p["lon"])
            if d <= radius:
                result[p["category"]].append(dict(p, distance_km=d))
        return {
            k: sorted(v, key=lambda p: p["distance_km"])[:limit] for k, v in result.items()
        }, covered

    def csv_export(self):
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["area_id", "nearby_locality", "score", "missing_factors"]
            + [k + "_score" for k in FACTORS]
        )
        for r in self.results:
            label = r["label"]
            label = "'" + label if label.startswith(("=", "+", "-", "@")) else label
            writer.writerow(
                [r["id"], label, r["score"], ",".join(r["missing"])]
                + [r["scores"][k] for k in FACTORS]
            )
        return out.getvalue().encode("utf-8")
