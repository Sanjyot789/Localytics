# Localytics

**Find an area that fits your priorities.**

Localytics is a Python application that helps people compare places to live using nearby transport, schools, healthcare, green spaces and air-quality observations. Instead of searching for a particular apartment, users choose what matters to them and explore how different areas compare.

Area recommendations currently cover **Delhi**, divided into **1,487 grid cells of approximately 1 km × 1 km**, clipped to the study boundary. The separate air-quality explorer supports other Indian cities represented in the government dataset.

> An area score describes the available evidence and the user's preferences. It is not an official liveability rating, an official AQI, or a guarantee that a location is suitable for housing.

## What you can do

- **Explore a shared map:** see area suitability, nearby facilities and air-monitor observations together, with zoom and reset controls.
- **Set your priorities:** adjust importance sliders, search radius, facility count cap, workplace location and must-have proximity requirements.
- **Find your best matches:** view the ten highest-ranked eligible areas and their score explanations.
- **Compare up to three areas:** add areas from their details panel and use **View comparison** to inspect factor scores side by side.
- **Search air quality by state and city:** fetch all result pages and inspect individual pollutants, even outside local transport coverage.
- **Find nearby transport:** search the downloaded OSM evidence for bus stops, metro stations and airport terminals without contacting Overpass.
- **Explore similar-area groups:** view precomputed clustering independently of the suitability ranking.
- **Export results:** save area scores as CSV and download clustering/evaluation reports.

The responsive Python interface uses **Flet** and **flet-map**. Tabs are built when opened, map cells are drawn around the current viewport, and existing controls are reused for selection updates. Rankings still consider every area in the study dataset.

## Quick start

Use **Python 3.13** for the documented setup and native build workflow. Source execution has also been checked in Python 3.14.

```bash
git clone https://github.com/Sanjyot789/Localytics.git
cd Localytics
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the app dependencies and launch:

```bash
python -m pip install -r requirements-app.txt
python main.py
```

This opens the desktop interface. The first desktop launch may download Flet's rendering client. `python app.py` is an alternative entry point for the same interface.

### Run in a browser

```bash
python main.py --web
```

Open **http://127.0.0.1:8550/**. Area recommendations are the default screen; the bottom navigation opens Air quality, Transport and About.

### Open on an iPhone or Android phone

Connect the phone and computer to the same Wi-Fi, then run on the computer:

```bash
python main.py --web --host 0.0.0.0
```

Find the computer's local network IP address. On the phone, open Safari or Chrome and enter:

```text
http://YOUR_COMPUTER_IP:8550
```

Use `http://`, include port `8550`, and keep the computer awake with the app running. Some campus or guest networks block connections between devices. This is the browser version; a separately installed phone app requires a native build.

## Air-quality API configuration

An API key is needed to refresh live air observations. It is not needed to explore the bundled area and facility data.

1. Obtain your own key from [data.gov.in](https://www.data.gov.in/).
2. Copy `.env.example` to `.env`.
3. Replace the placeholder in `.env`:

```dotenv
DATA_GOV_API_KEY=YOUR_API_KEY_HERE
```

You can also enter a key on the Air quality screen for the current session. Session-entered keys are not written to the evidence database or exports. Keep `.env` private; `.env.example` contains a placeholder only.

The Python app uses certificate-verified HTTPS and does not require a `curl` executable on phones. Government API requests can be slow or fail temporarily; a failed refresh leaves previously cached readings available with their timestamps.

## Factors and scoring

| Factor | Evidence used |
|---|---|
| Air quality | Nearby eligible PM2.5 monitor reading |
| Bus and metro | Mapped bus-stop and metro-station access |
| School proximity | Mapped schools; proximity only |
| Hospitals | Mapped hospital access |
| Public green spaces | Mapped parks, subject to access information |
| Gyms | Mapped gym access |
| Malls | Mapped shopping-mall access |
| EV charging | Mapped charging facilities |
| Airport terminals | Mapped terminal access within 25 km |
| Workplace distance | Straight-line distance to the user-selected destination |

Importance sliders range from **0 (ignore)** to **5 (very important)**. Positive priorities are normalised to sum to one:

```text
normalised_weight = factor_priority / sum_of_positive_priorities
area_score = 100 × sum(normalised_weight × factor_score)
```

Factor scores range from 0 to 1, with higher values indicating a better match:

- **Local services:** equal parts nearest-distance score and nearby-count score. Users can choose a 1, 2 or 5 km radius and a count cap of 5, 10 or 20. Distance is measured from the grid cell's centre.
- **Daily transit:** the mean of bus-stop and metro-station factor scores.
- **Workplace:** `1 - min(distance_km / 50, 1)`.
- **PM2.5 indicator:** `1 - min(value / 250, 1)`. The cap is a project normalisation choice, not a health threshold or official AQI conversion. Ranking requires a valid, non-negative reading from a monitor within 5 km and 6 hours; future readings are rejected.

Cells with missing positively weighted evidence or failed/unverified must-have requirements are excluded from the ranked results. Weights are not silently redistributed for each cell. Displayed monitor context may be older or farther away than the monitor eligible for scoring; the app distinguishes these roles.

Clustering helps users discover similar areas. Cluster labels do not add a bonus to the suitability score. Missing-value filling and scaling are confined to the clustering pipeline.

## Data, coverage and limitations

The repository includes a prebuilt SQLite database, so startup does not require processing PBF files or making an API request. Recommendations and mapped facilities work from local data; live API calls and background map tiles need internet access.

- **Area recommendations:** Delhi only. A cell can include non-residential land and is a comparison unit, not a confirmed housing location.
- **Transport and amenities:** limited to the downloaded OSM extracts. Extract bounds indicate extent, not guaranteed completeness. No mapped result does not prove no facility exists.
- **Air-quality search:** independent of transport coverage and available for cities represented in the national dataset.
- **Schools:** proximity is available; verified school quality, admissions, board and stage matching are not.
- **Other factors:** water quality, crime, affordability, population density and routed commute times are not currently scored.
- **Distances:** straight-line distances, not walking routes or travel times. EV connector suitability, hospital capability, public access and passenger airport service are not guaranteed.
- **Place labels:** nearby mapped locality names are orientation aids, not official grid-cell names or neighbourhood boundaries.

The area pipeline merges overlapping extracts by OSM object type/ID, preferring the highest available version/timestamp. It also consolidates nearby same-name facilities. Unnamed or inconsistently mapped duplicates can remain.

## Native apps and deployment

The UI and application logic are written in Python. Flet supplies the Flutter/browser renderer and platform packaging.

| Target | Current route |
|---|---|
| Browser | Python-hosted web app through `main.py --web` or ASGI |
| Windows / macOS | Run from Python; native build configuration is included |
| Android | Browser access or a platform APK/AAB build |
| iPhone / iPad | Safari access or a signed iOS build using macOS and Xcode |

Native installer configurations are included, but native release packages have not been built and device-tested across all platforms. Platform SDKs, signing and distribution requirements still apply.

See [CROSS_PLATFORM.md](CROSS_PLATFORM.md) for native builds, the manual GitHub build workflow, app-private storage and deployment details.

For a Python-hosted web deployment:

```bash
uvicorn server:app --host 0.0.0.0 --port 8550
```

Public hosting needs HTTPS and WebSocket support. A `Dockerfile` is included. This project is configured for dynamic Python hosting, not a verified static/Pyodide export.

## Rebuild the area evidence

Install the full analysis dependencies before processing source extracts:

```bash
python -m pip install -r requirements.txt
python scripts/build_areas.py /path/to/delhi.pbf /path/to/other1.pbf
python scripts/evaluate_areas.py
```

These commands generate the SQLite evidence, manifest and model/evaluation reports. Rebuilding replaces the generated database, including its cached air readings. Refresh air observations afterwards and restart the app to load the new data.

Before producing a native package, prepare a clean bundled copy:

```bash
python scripts/prepare_app.py
```

This copies public evidence into `assets/datasets/` and clears the query cache in the copy. It does not include `.env` or alter the source database. Native devices reuse precomputed clusters rather than installing the offline analysis stack.

Adding recommendations for another city requires appropriate extracts, a validated boundary, the correct projected coordinate system and a new evidence build.

## Development and tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover scoring, missing evidence, air pagination, city isolation, OSM merging, responsive controls, map navigation, viewport culling, comparison interactions, exports and browser sessions. API tests use synthetic responses; cache tests use temporary evidence copies.

The current full suite has a known transport-metadata mismatch: `tests/test_overlap.py` expects `overlap_duplicates_removed`, which is absent from the current transport metadata. This does not prevent the app from starting, but the full test suite is not entirely passing.

Model reports describe clustering separation/stability and ranking sensitivity. They do not establish prediction accuracy or user recommendation quality. The proposed user study has not yet been completed.

### Main files

| Location | Purpose |
|---|---|
| `main.py`, `server.py` | Desktop/browser entry point and ASGI server |
| `native_app/` | Python UI, session operations and native storage |
| `areas.py`, `preferences.py` | Factor scoring, ranking and input validation |
| `air_client.py`, `observations.py` | Government API access and monitor observations |
| `data_store.py`, `data/` | SQLite evidence, cache, manifests and reports |
| `osm_data.py`, `scripts/` | Offline OSM processing, evaluation and packaging |
| `clustering.py` | Offline clustering and model reports |
| `tests/` | Regression and interaction tests |
| `templates/`, `static/`, `unified_map.py` | Compatibility Flask/Folium interface |

The earlier Flask website remains available:

```bash
python -m pip install -r requirements.txt
flask --app app run
```

It runs at **http://127.0.0.1:5000/** and retains the area, air-quality, transport and export routes.

## Sources and licences

- **Facilities and background maps:** [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. Extract fingerprints and bounds are recorded in `data/area_manifest.json`; original download dates are unverified.
- **Delhi boundary:** [DataMeet Municipal Spatial Data](https://github.com/datameet/Municipal_Spatial_Data/tree/master/Delhi), [CC BY-SA 2.5 India](https://creativecommons.org/licenses/by-sa/2.5/in/). Source notes are preserved in `data/boundary_source.md`. This community reference is not a certified legal boundary.
- **Air observations:** [Real-time air-quality dataset on data.gov.in](https://www.data.gov.in/resource/real-time-air-quality-index-various-locations).
- **Project code:** see [LICENSE](LICENSE).

Developed as **Group 7's Python analytics project**.
