# Localytics

Local air-quality exploration and preference-based area recommendations.

## Run the Python app

Localytics now has one Python interface for the browser and for native Android, iOS, Windows and macOS builds. The interface uses Flet and flet-map; the existing analysis and scoring remain Python. See [CROSS_PLATFORM.md](CROSS_PLATFORM.md) for the build requirements and current verification limits.

Use Python 3.13 in a virtual environment:

```bash
python -m pip install -r requirements-app.txt
python main.py
```

For the browser version:

```bash
python main.py --web
```

The browser address is http://127.0.0.1:8550/. The default screen is area recommendations; the bottom navigation opens nationwide air-quality search, nearby transport and the methodology/reports. `python app.py` also starts the new app.

Your existing `.env` stays local/server-side. Set `DATA_GOV_API_KEY` there for air refreshes, or enter a key for the current session on the Air quality screen. Native packages exclude `.env` and ship a public evidence database with its air-query cache cleared. Area recommendations work offline; map tiles and live readings need internet access.

### Previous Flask interface

The previous website is retained for compatibility:

```bash
python -m pip install -r requirements.txt
flask --app app run
```

Its homepage is http://127.0.0.1:5000/, and `/air-quality`, `/areas` and the existing API/export routes remain available. Its templates and Folium maps are not needed by the new native app.

## What is integrated

- 1 km Delhi grid in EPSG:32643, clipped to a source-documented reference boundary, with stable IDs and nearby locality labels.
- Schools, hospitals, accessible/unknown-access parks, gyms, malls, charging points, bus stops, metro stations and airport terminals extracted from both local PBF files.
- Overlap removal by OSM type/ID, retaining highest version/timestamp; same-name facilities consolidated within 100 m. Unknown/unnamed duplicates can remain.
- SQLite storage with an R-tree facility index, source fingerprints and extraction metadata.
- Feature counts, nearest straight-line distances and up to five nearest features per category, at 1/2/5 km local radii and 25 km for airport terminals.
- User importance sliders, optional workplace map selection, must-have proximity filters, transparent weighted scores, top-ten shortlist and comparison of up to three areas.
- Map colours for scores or similar-area groups; selected nearby services and cached air monitors on the same map.
- Separate K-Means/hierarchical clustering with silhouette comparison and five resampling stability checks; no cluster bonus in ranking.
- CSV download, repeatable baseline/sensitivity report and regression tests.

## Missing data and air quality

The original air-quality search supports other cities independently of local transport coverage. Successful searches are saved in the local database; Delhi state refreshes provide monitor context for the area page. Use **Refresh Delhi air readings** to obtain observations. It requires the existing API key and may take a few minutes. Cached readings show their own timestamps; an API failure does not erase the previous cache.

Pollution readings are displayed even when transport information is absent. The enabled air-quality slider uses the API's PM2.5 value as a project indicator: lower is better. Its factor score is `1 - min(value / 250, 1)` (displayed on a 0–100 scale). The cap is a project normalisation choice, not a health threshold or official AQI conversion; units and averaging period are not assumed. Ranking uses the nearest valid PM2.5 monitor within 5 km and 6 hours and rejects negative, invalid or future readings. Without an eligible reading, a positively weighted air factor makes the cell unranked. Displayed nearest-monitor context may be older or farther away and is labelled separately from the actual scoring monitor. No verification environment flag is required.

All positive-weight factors need observed evidence. Missing selected factors or failed/unverified must-have checks exclude the cell from the ranked shortlist. Weights are never silently redistributed per cell. Imputed/scaled values exist only inside clustering.

Extract bounds indicate geographic extent, not guaranteed OSM completeness. Scores measure available mapped evidence. No mapped facility is not proof no facility exists. Schools are proximity only: there is no verified school-quality score or stage/board matching. Public EV access, connector compatibility, hospital capability, airport passenger service and admissions are not guaranteed. Private/no-access features are excluded; unknown access is disclosed.

Grid cells can include industrial, agricultural or other non-residential land; they are comparison units, not confirmed housing locations. Locality labels are nearest mapped names, not official cell names. The boundary is a community reference, not a legal boundary. Distances are not commute minutes. Water, crime, affordability, density and school quality stay disabled pending suitable evidence. No user feedback or recommendation accuracy has been invented.

## Rebuild from PBF files

```bash
python scripts/build_areas.py /path/to/delhi.pbf /path/to/other1.pbf
python scripts/evaluate_areas.py
```

The build produces `data/areas.sqlite` and `data/area_manifest.json`. It reads nodes and ways; relation-only facilities may be absent. A rebuild replaces the generated database, including its cached air readings. Refresh air afterwards. Restart Flask after rebuilding to clear its in-memory area cache. `evaluate_areas.py` produces `evaluation_report.json` and `cluster_report.json`, which allows the app to load precomputed clustering immediately. Every model report is tied to the data-build version.

Only the Delhi recommendation boundary is bundled. Nationwide station searches remain available. To add another recommendation city, supply its boundary, choose the correct projected CRS and rebuild with validated coverage; do not simply apply Delhi's grid to another city.

## Tests and evaluation

```bash
python -m pip install pytest
python -m pytest -q
```

Tests cover the original city searches and map, missing transport files, case handling, feature classification, score direction, disabled factors, missing evidence, must-have pass/fail/unverified rules, stale/distant air data, CSV export and independent clustering. Tests use synthetic API records and do not need the live API. Reports compare default/equal/single-factor rankings and changes to radius/count cap. Clustering reports silhouette and adjusted Rand agreement across resamples, not prediction accuracy. The planned 12-person usability study still needs real participants.

## Sources and licences

Facilities: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright (ODbL). The supplied `delhi.pbf` and `other1.pbf` fingerprints and header bounds are recorded in `data/area_manifest.json`; original download dates are unverified.

Boundary: DataMeet Municipal Spatial Data, https://github.com/datameet/Municipal_Spatial_Data/tree/master/Delhi . CC BY-SA 2.5 India, https://creativecommons.org/licenses/by-sa/2.5/in/ . Original source and licence notes are preserved in `data/boundary_source.md`. The boundary was checked for geometry validity and projected area plausibility; this is not legal certification.

Air observations: https://www.data.gov.in/resource/real-time-air-quality-index-various-locations . Background tiles: OpenStreetMap. The area database works locally; web maps still need internet for their tiles and Leaflet assets.


## Code organisation

- `main.py`, `server.py`: Python desktop/browser entry points and ASGI deployment.
- `native_app/`: responsive Python controls, per-session operations and private native storage.
- `preferences.py`: shared input validation for the Python and Flask interfaces.
- `scripts/prepare_app.py`, `scripts/build_app.py`: clean evidence bundling and native packaging.
- `app.py`: Flask setup and station/transport routes.
- `area_views.py`: homepage, area detail API and downloads.
- `air_client.py`: paginated API requests and case-tolerant city filtering.
- `data_store.py`: SQLite area access and cached air readings.
- `areas.py`: factor scoring, must-have checks and personalised ranking.
- `clustering.py`: independent area clustering and model reports.
- `observations.py`: shared station grouping, latest PM2.5 parsing and display bands.
- `geography.py`: coordinate validation, distances, extent checks and named-facility consolidation.
- `osm_data.py`: common OSM reader, classification and overlap merging for both extraction commands.
- `transport_data.py`, `transport.py`, `connectivity/nearest.py`: CSV loading, transport rendering and nearby lookup.
- `unified_map.py`: Folium map construction; map behaviour lives in `templates/combined_map.js.j2`.
- `config.py`: shared labels, colours, paths and scoring constants.
- `templates/`: Jinja pages with a common base/navigation; `static/`: page scripts and styles.
- `scripts/`: offline area rebuild and evaluation commands.
- `tests/`: regression tests. Test discovery excludes generated data and archived files.

The unused standalone `mapping.py` renderer and hardcoded nearest-search demonstration were removed. The compatibility Flask interface retains these routes: `/`, `/areas`, `/air-quality`, `/connectivity` and area APIs/downloads.

For development checks:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
```

Tests preserve cached observations. Refactoring does not require rebuilding your existing database or changing `.env`. Restart your own Flask process after replacing code; the development server is not started by tests.

Prior source files and old in-project backups were archived at `/Users/sam/Documents/Codex/2026-10-16/how-x20/outputs/Localytics_before_refactor_2026-10-24.zip`. This archive excludes credentials; your original `.env` stays in the project.
