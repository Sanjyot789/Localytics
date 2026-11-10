"""Preference validation shared by every interface."""

import math

from config import COUNT_CAPS, DEFAULTS, FACTORS, LOCAL_RADII
from geography import coordinates


def preferences(values):
    weights = {k: float(values.get("w_" + k, DEFAULTS.get(k, 0))) for k in FACTORS}
    if any(not math.isfinite(w) or not 0 <= w <= 5 for w in weights.values()):
        raise ValueError("Importance must be between 0 and 5.")
    if not any(weights.values()):
        raise ValueError("Choose at least one factor with positive importance.")
    radius = int(values.get("radius", 2))
    cap = int(values.get("cap", 10))
    if radius not in LOCAL_RADII or cap not in COUNT_CAPS:
        raise ValueError("Select one of the listed radii and count caps.")
    workplace = None
    lat = values.get("work_lat", "").strip()
    lon = values.get("work_lon", "").strip()
    if lat or lon:
        workplace = coordinates(lat, lon)
    if weights["workplace"] > 0 and workplace is None:
        raise ValueError("Select a workplace on the map or enter its coordinates.")
    must = {}
    for cat in ("metro_station", "school", "hospital", "park", "ev"):
        raw = values.get("must_" + cat, "").strip()
        if raw:
            d = float(raw)
            if not math.isfinite(d) or not 0.1 <= d <= radius:
                raise ValueError(
                    "Must-have distances must be from 0.1 km to the selected local radius."
                )
            must[cat] = d
    return weights, radius, cap, workplace, must
