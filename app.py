"""Legacy Flask compatibility routes. python app.py starts the cross-platform Python app."""

import math

from dotenv import load_dotenv
from flask import Flask, render_template, request

import air_client
import data_store
from area_views import register as register_area_views
from config import ROOT, TRANSPORT_CATEGORIES
from geography import coordinates
from transport import search_transport, transport_map
from unified_map import build_map

load_dotenv(ROOT / ".env")
app = Flask(__name__)


@app.route("/air-quality", methods=["GET", "POST"])
def index():
    state, city = "", ""
    error = None
    map_html = None
    count = station_count = skipped = 0
    loaded = False
    if request.method == "GET":
        map_html, _, _ = build_map([])
    if request.method == "POST":
        state = request.form.get("state", "").strip()
        city = request.form.get("city", "").strip()
        try:
            if not state or len(state) > 100 or len(city) > 100:
                raise air_client.FetchError(
                    "Enter a state, and keep each filter under 100 characters."
                )
            records = air_client.fetch_records(state, city)
            data_store.cache_air(state, city, records)
            count = len(records)
            loaded = True
            map_html, station_count, skipped = build_map(records)
        except air_client.FetchError as exc:
            error = str(exc)
    return render_template(
        "index.html",
        state=state,
        city=city,
        error=error,
        map_html=map_html,
        count=count,
        station_count=station_count,
        skipped=skipped,
        loaded=loaded,
    )


@app.route("/connectivity", methods=["GET", "POST"])
def connectivity():
    lat, lon, radius, limit = "", "", 5.0, 5
    error, map_html, results = None, None, None
    try:
        if request.method == "POST":
            lat, lon = coordinates(
                request.form.get("latitude", ""), request.form.get("longitude", "")
            )
            radius = float(request.form.get("radius", ""))
            limit = int(request.form.get("limit", ""))
            if not (math.isfinite(radius) and 0.1 <= radius <= 100 and 1 <= limit <= 20):
                raise ValueError
            results = search_transport(lat, lon, radius, limit)
            map_html = transport_map(lat, lon, results, radius)
    except (ValueError, OverflowError):
        error = (
            "Enter valid coordinates, a radius from 0.1 to 100 km, and 1–20 results per category."
        )
        lat, lon, radius, limit = "", "", 5.0, 5
    except OSError:
        error = (
            "Local transport data is missing. Restore the connectivity folder from the download."
        )
    return render_template(
        "connectivity.html",
        lat=lat,
        lon=lon,
        radius=radius,
        limit=limit,
        error=error,
        results=results,
        map_html=map_html,
        categories=TRANSPORT_CATEGORIES,
    )


register_area_views(app)

if __name__ == "__main__":
    from main import launch

    launch()
