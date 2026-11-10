"""Flask views for offline area exploration and preference-based recommendations."""

import csv
import io
import sqlite3

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import air_client
import areas
import clustering
import data_store
from config import DEFAULTS, FACILITY_COLORS, FACTORS
from observations import monitors, severity
from preferences import preferences

bp = Blueprint("areas", __name__)


def station_context():
    records, fetched = data_store.air_records()
    return monitors(records), fetched


@bp.route("/areas")
@bp.route("/")
def explore():
    error = None
    try:
        cells, manifest = data_store.dataset()
    except (OSError, sqlite3.Error):
        return render_template(
            "areas.html",
            ready=False,
            error="Area data is missing. Run scripts/build_areas.py with your PBF files.",
        ), 503
    try:
        weights, radius, cap, workplace, must = preferences(request.args)
    except (ValueError, OverflowError) as exc:
        error = str(exc)
        weights, radius, cap, workplace, must = dict(DEFAULTS), 2, 10, None, {}
    records, air_fetched = data_store.air_records()
    stations = monitors(records)
    results = areas.rank(cells, weights, radius, cap, stations, workplace, must)
    by_id = {r["id"]: r for r in results}
    groups = (
        clustering.clustering()
        if request.args.get("clusters") == "1"
        else dict(available=False, labels={}, trials=[])
    )
    polygons = []
    for cell in cells:
        r = by_id[cell["id"]]
        polygons.append(
            dict(
                type="Feature",
                geometry=cell["geometry"],
                properties=dict(
                    id=cell["id"],
                    label=cell["label"],
                    score=r["score"],
                    group=groups["labels"].get(cell["id"]),
                    missing=len(r["missing"]),
                ),
            )
        )
    eligible = [r for r in results if r["score"] is not None]
    notice = request.args.get("notice", "")
    if notice == "refreshed":
        notice = "Delhi air-quality data refreshed. Observation age is checked separately from download time."
    elif notice == "air_error":
        notice = (
            "The air-quality API could not be refreshed. Existing cached readings remain available."
        )
    else:
        notice = ""
    browser_preferences = {f"w_{k}": weights.get(k, 0) for k in FACTORS}
    browser_preferences.update(radius=radius, cap=cap)
    if workplace:
        browser_preferences.update(work_lat=workplace[0], work_lon=workplace[1])
    browser_preferences.update({f"must_{k}": v for k, v in must.items()})
    browser_config = dict(
        geojson=dict(type="FeatureCollection", features=polygons),
        factorNames=FACTORS,
        weights=weights,
        preferences=browser_preferences,
        workplace=workplace,
        facilityColors=FACILITY_COLORS,
        airPoints=[
            dict(
                name=s["name"],
                lat=s["lat"],
                lon=s["lon"],
                pm=s["pm"],
                air=severity(s["pm"]),
                updated=s["stamp"].isoformat() if s["stamp"] else None,
            )
            for s in stations
        ],
    )
    return render_template(
        "areas.html",
        ready=True,
        error=error,
        notice=notice,
        factors=FACTORS,
        weights=weights,
        radius=radius,
        cap=cap,
        workplace=workplace,
        must=must,
        manifest=manifest,
        top=eligible[:10],
        usable=len(eligible),
        excluded=len(results) - len(eligible),
        air_count=len(records),
        air_fetched=air_fetched,
        groups=groups,
        browser_config=browser_config,
        evaluation=data_store.read_report("evaluation_report.json"),
    )


@bp.route("/api/areas/<cell_id>")
def detail(cell_id):
    try:
        weights, radius, cap, workplace, must = preferences(request.args)
    except (ValueError, OverflowError) as exc:
        return jsonify(error=str(exc)), 400
    cells, _ = data_store.dataset()
    cell = next((c for c in cells if c["id"] == cell_id), None)
    if not cell:
        abort(404)
    stations, _ = station_context()
    result = areas.evaluate(cell, weights, radius, cap, stations, workplace, must)
    return jsonify(result)


@bp.route("/areas/export.csv")
def export():
    try:
        weights, radius, cap, workplace, must = preferences(request.args)
    except (ValueError, OverflowError) as exc:
        return str(exc), 400
    cells, _ = data_store.dataset()
    stations, _ = station_context()
    results = areas.rank(cells, weights, radius, cap, stations, workplace, must)
    stream = io.StringIO()
    writer = csv.writer(stream)
    keys = list(FACTORS)
    writer.writerow(
        [
            "area_id",
            "nearby_locality",
            "latitude",
            "longitude",
            "suitability_score",
            "missing_factors",
        ]
        + [k + "_score" for k in keys]
    )
    for r in results:
        # Prevent spreadsheet formulas in user-sourced place labels.
        label = r["label"]
        label = "'" + label if label.startswith(("=", "+", "-", "@")) else label
        writer.writerow(
            [r["id"], label, r["lat"], r["lon"], r["score"], ",".join(r["missing"])]
            + [r["scores"][k] for k in keys]
        )
    return Response(
        stream.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=localytics_areas.csv"},
    )


@bp.get("/areas/evaluation.json")
def evaluation_report():
    path = data_store.DB.with_name("evaluation_report.json")
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name="localytics_evaluation.json")


def register(app):
    app.register_blueprint(bp)

    @app.post("/areas/refresh-air")
    def refresh_area_air():
        try:
            records = air_client.fetch_records("Delhi", "")
            data_store.cache_air("Delhi", "", records)
        except air_client.FetchError:
            return redirect(url_for("areas.explore", notice="air_error"))
        return redirect(url_for("areas.explore", notice="refreshed"))
