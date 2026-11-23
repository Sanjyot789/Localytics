"""Local bridge to the existing Localytics Python engine."""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("localytics", type=Path)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    sys.path.insert(0, str(args.localytics.resolve()))

    from areas import evaluate
    from config import FACTORS
    from native_app.service import LocalyticsService, Selection
    from preferences import preferences

    service = LocalyticsService(args.localytics / "data/areas.sqlite")

    def preferences_arguments(values):
        weights, radius, cap, workplace, must = preferences(values)
        return weights, radius, cap, service.stations, workplace, must

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            status = 200
            if url.path == "/api/localytics/grid":
                body = {
                    "factors": FACTORS,
                    "grid": {
                        "type": "FeatureCollection",
                        "features": [
                            {"id": i, "type": "Feature", "geometry": cell["geometry"],
                             "properties": {"area": cell["id"]}}
                            for i, cell in enumerate(service.cells)
                        ],
                    },
                    "groups": service.clusters().get("labels", {}),
                }
            elif url.path == "/api/localytics/rank":
                try:
                    service.reload_air()
                    service.apply(Selection(*preferences(dict(parse_qsl(url.query)))))
                    body = {"areas": [
                        {"id": row["id"], "label": row["label"], "score": row["score"],
                         "pm": row["air"]["scoring_value"] if row["air"] else None}
                        for row in service.results
                    ],
                            "air_fetched": service.air_fetched}
                except ValueError as exc:
                    status, body = 400, {"error": str(exc)}
            elif url.path == "/api/localytics/area":
                values = dict(parse_qsl(url.query))
                cell = service.cells_by_id.get(values.get("id"))
                if cell is None:
                    status, body = 404, {"error": "Area unavailable."}
                else:
                    try:
                        body = evaluate(cell, *preferences_arguments(values))
                    except ValueError as exc:
                        status, body = 400, {"error": str(exc)}
            else:
                status, body = 404, {"error": "Unknown endpoint."}
            payload = json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
