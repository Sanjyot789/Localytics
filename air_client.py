"""Paginated data.gov.in access, with Python HTTPS for mobile and curl compatibility."""

import json
import os
import shutil
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"


class FetchError(Exception):
    pass


def _curl_page(params):
    config = "url = " + json.dumps(BASE_URL + "?" + urlencode(params)) + "\n"
    try:
        result = subprocess.run(
            [
                "curl",
                "--config",
                "-",
                "--silent",
                "--show-error",
                "--fail",
                "--connect-timeout",
                "15",
                "--max-time",
                "120",
                "-H",
                "accept: application/json",
            ],
            input=config,
            capture_output=True,
            text=True,
            timeout=125,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise FetchError("The API connection failed or timed out. Please try again.") from None
    if result.returncode:
        raise FetchError(
            "The API request failed (possibly a timeout or HTTP 502). Please try again."
        )
    return result.stdout


def _python_page(params):
    import ssl

    import certifi

    context = ssl.create_default_context(cafile=certifi.where())
    request = Request(
        BASE_URL + "?" + urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "Localytics/1.0"},
    )
    try:
        with urlopen(request, timeout=120, context=context) as response:
            return response.read().decode("utf-8")
    except (OSError, HTTPError, URLError, UnicodeError):
        # Raw request exceptions can contain the URL/API key; never surface them.
        raise FetchError(
            "The air-quality API could not be reached. Check your connection or try again."
        ) from None


def _paginate(state, city, key, request_page):
    if not key:
        raise FetchError(
            "Set DATA_GOV_API_KEY in your .env file, or enter your API key in the app."
        )
    params = {"api-key": key, "format": "json", "limit": 100, "offset": 0, "filters[state]": state}
    if city:
        params["filters[city]"] = city
    records = []
    seen = set()
    for _ in range(200):
        try:
            data = json.loads(request_page(params))
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError
            batch = data["records"]
            if any(not isinstance(row, dict) for row in batch):
                raise ValueError
            total = int(data["total"]) if data.get("total") is not None else None
            if total is not None and total < 0:
                raise ValueError
        except (ValueError, TypeError):
            raise FetchError("The API returned an unexpected response. Please try again.") from None
        if not batch:
            if total is not None and len(records) < total:
                raise FetchError("The API stopped before returning all records. Please try again.")
            return records
        signature = json.dumps(batch, sort_keys=True)
        if signature in seen:
            raise FetchError("The API repeated a page. Fetch stopped to avoid duplicate data.")
        seen.add(signature)
        records.extend(batch)
        params["offset"] += len(batch)
        if total is not None and len(records) >= total:
            return records
    raise FetchError("The query exceeded 200 pages. Please narrow it to a city.")


def _filtered_fetch(state, city, fetch):
    state = " ".join(state.split())
    city = " ".join(city.split())
    if not state or len(state) > 100 or len(city) > 100:
        raise FetchError("Enter a state and keep each filter under 100 characters.")
    records = fetch(state, city)
    if records:
        return records
    canonical = state.title()
    if canonical != state:
        records = fetch(canonical, city)
        if records:
            return records
    if city:
        return [
            r
            for r in fetch(canonical, "")
            if " ".join(str(r.get("city", "")).split()).casefold() == city.casefold()
        ]
    return []


def _fetch_records(state, city):
    return _paginate(
        state,
        city,
        os.environ.get("DATA_GOV_API_KEY", "").strip(),
        _curl_page if shutil.which("curl") else _python_page,
    )


def fetch_records(state, city):
    return _filtered_fetch(state, city, _fetch_records)


class PythonAirClient:
    """Credentials stay in this session; no curl executable is needed on phones."""

    def __init__(self, api_key=None):
        self.api_key = (
            api_key if api_key is not None else os.environ.get("DATA_GOV_API_KEY", "")
        ).strip()

    def fetch_records(self, state, city=""):
        return _filtered_fetch(
            state, city, lambda s, c: _paginate(s, c, self.api_key, _python_page)
        )
