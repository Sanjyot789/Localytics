# Localytics: browser, phone and desktop app

The application interface, event handlers, data access, scoring and exports are written in Python. Flet supplies the Flutter/browser rendering layer and native packaging. A native app still contains a platform runtime; Python alone does not create an Android APK or an Apple-signed app.

## Run locally

Use Python 3.13 in a virtual environment, then:

```bash
python -m pip install -r requirements-app.txt
python main.py
```

This opens the desktop app. `python app.py` is an equivalent shortcut.

```bash
python main.py --web
```

This opens the Python-hosted browser app at http://127.0.0.1:8550/. To open it from a phone on the same network, run `python main.py --web --host 0.0.0.0` and visit the computer's network address on port 8550. Use a trusted network. For public access, deploy the server behind HTTPS.

Stop a locally launched app with Ctrl+C. No development server is started by installing dependencies, running tests or preparing a package.

## Screens and retained features

| Screen | Features |
|---|---|
| Areas (default) | 1,487 Delhi grid cells, ten priority sliders, must-have filters, workplace selection, suitability/groups map, score explanations, nearby facilities, monitor observations, top-ten shortlist and three-area comparison |
| Air quality | State/city search across the national dataset, all API pages, monitor map, pollutant readings, independent of local OSM coverage |
| Transport | Coordinate search for bus stops, metro stations and airport terminals, nearest facilities and extract coverage information |
| About | Scoring method, evidence limitations, data attribution, clustering/evaluation reports and export controls |

CSV and report exports use the device/browser save dialog. On a narrow screen the preferences collapse and the map/details stack vertically. The analysis uses the same scoring functions as the previous Flask app.

Only Delhi area recommendations and the existing OSM coverage are bundled. This conversion does not add new cities' facilities, verified school quality, water, crime, rents or commute-time data. The Air quality search continues to support other cities.

## Build installable apps

Install the build tools and prepare a clean copy of the public data:

```bash
python -m pip install ".[build]"
python scripts/prepare_app.py
```

The preparation script copies `data/areas.sqlite` into `assets/datasets/`, removes the air-query cache from that copy and copies the data reports. It does not change the original database or include `.env`.

| Target | Build command | Requirements |
|---|---|---|
| Android APK | `python scripts/build_app.py apk` | Android SDK, Java/build tools and accepted SDK licences |
| Android Play bundle | `python scripts/build_app.py aab` | Android build tools and release signing for publication |
| iOS simulator | `python scripts/build_app.py ios-simulator` | macOS, full Xcode and its simulator components |
| iPhone/iPad | `python scripts/build_app.py ipa` | macOS, full Xcode, Apple signing/provisioning for device distribution |
| macOS | `python scripts/build_app.py macos` | macOS and full Xcode; signing/notarisation for distribution |
| Windows | `python scripts/build_app.py windows` | Windows and the desktop C++/Flutter build prerequisites |

Append `--check` to inspect preliminary prerequisites without building. Flet manages its matching Flutter version; an unrelated installed Flutter version may not be sufficient. Native builds use Python 3.13. Build outputs go under `build/<target>/`.

The manual GitHub workflow in `.github/workflows/build-apps.yml` defines Windows, macOS, Android and iOS-simulator jobs. It has not been run or published. It requires the source evidence database to be present in the checked-out project. An iOS simulator package cannot be installed on a physical iPhone; a signed IPA is a separate build.

**Verification status:** the shared engine, desktop/phone-width Python controls, control serialization, browser ASGI session and regression tests have been checked locally. Native installers have not been built or device-tested. This Mac lacks full Xcode, and a Windows package requires a Windows build host. A successful preliminary Android check does not replace an APK build or device test.

## Deploy the browser app

The browser version runs Python on a server. For a deployment service with an ASGI start command:

```bash
python -m pip install -r requirements-app.txt
uvicorn server:app --host 0.0.0.0 --port 8550
```

Use HTTPS and WebSocket support in the hosting proxy. Set `DATA_GOV_API_KEY` as a server environment variable and persist `data/` if cached readings should survive restarts. `Dockerfile` provides the same dynamic server. Keep one worker initially; the SQLite cache is shared while preferences and API-key input belong to each session. This project is not configured or verified as a static/Pyodide web export; do not substitute `flet build web` for this server deployment.

## Storage and API access

- Source/server runs retain `data/areas.sqlite` and its existing cache.
- Native builds copy the bundled evidence into the platform's writable app-data folder on first launch. Data upgrades preserve the local air cache.
- Native HTTPS uses Python's standard library with certificate verification; the app does not need `curl` installed.
- A key entered in Air quality is kept in that session's memory, never shown in exports or written to the evidence database. The field clears after a successful request. A packaged app does not receive the development `.env`.
- Recommendations, facilities and the precomputed clusters work from the local database. Live air data and OpenStreetMap tiles require internet access. Previously cached readings remain available with timestamps after a refresh failure.
- Analysis dependencies such as osmium, Shapely, SciPy and scikit-learn remain in the separate offline/legacy requirements. Phones load the precomputed cluster report instead of retraining a model.

After rebuilding evidence on the analysis computer, regenerate the reports and run `prepare_app.py` before producing new native packages. Existing installed packages do not automatically download a new evidence database.

Framework references: [Flet publishing](https://flet.dev/docs/publish/), [Python-hosted web deployment](https://flet.dev/docs/publish/web/dynamic-website/), [Flet map](https://flet.dev/docs/controls/map/).
