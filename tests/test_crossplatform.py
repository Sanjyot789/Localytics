import asyncio
import json
import sqlite3
import tomllib
from types import SimpleNamespace

import msgpack
import pytest
from flet.controls.base_control import BaseControl
from flet.messaging.protocol import configure_encode_object_for_msgpack

import air_client
from config import DATA_DIR, ROOT
from data_store import AreaRepository
from native_app.runtime import prepare_runtime
from native_app.service import LocalyticsService, Selection
from native_app.ui import LocalyticsApp


class FakePage:
    def __init__(self, width=1200, web=False):
        self.width = width
        self.web = web
        self.updates = 0

    def update(self):
        self.updates += 1

    def add(self, *controls):
        self.controls = controls


@pytest.fixture
def service():
    return LocalyticsService(DATA_DIR / "areas.sqlite")


def test_python_ui_phone_and_desktop(service):
    for width in (390, 1200):
        page = FakePage(width)
        ui = LocalyticsApp(page, service)
        ui.mount()
        assert ui.area_map.height == (360 if width == 390 else 470)
        assert ui.preferences_panel.expanded == (width >= 700)
        assert 0 < len(ui.polygon_layer.polygons) <= len(service.cells) + 1
        ui.select(service.shortlist[0]["id"])
        ui.toggle_compare(service.shortlist[0]["id"])
        assert len(service.comparison) == 1
        payload = msgpack.packb(
            [page.controls, page.navigation_bar],
            default=configure_encode_object_for_msgpack(BaseControl),
            use_bin_type=True,
        )
        assert len(payload) > 1000
        ui.toggle_compare(service.shortlist[0]["id"])
        for index in range(4):
            ui.navigate(SimpleNamespace(control=SimpleNamespace(selected_index=index)))
            assert ui.body.controls == [ui.sections[index]]


def test_python_ui_preferences_and_compare_limit(service):
    page = FakePage()
    ui = LocalyticsApp(page, service)
    ui.mount()
    ui.weights["park"].value = 5
    asyncio.run(ui.apply())
    assert service.selection.weights["park"] == 5
    cell = service.shortlist[0]
    assert service.select_at(cell["lat"], cell["lon"])["id"] == cell["id"]
    assert service.select_at(18.52, 73.85) is None
    for row in service.shortlist[:3]:
        service.compare(row["id"])
    with pytest.raises(ValueError, match="three"):
        service.compare(service.shortlist[3]["id"])
    with pytest.raises(ValueError):
        service.apply(Selection(weights={"park": 0}))
    assert b"area_id" in service.csv_export()


def test_repository_instances_do_not_mix_paths(tmp_path):
    for city in ("Delhi", "Pune"):
        database = tmp_path / (city + ".sqlite")
        with sqlite3.connect(database) as db:
            db.execute(
                "CREATE TABLE air_cache(query TEXT PRIMARY KEY,fetched_at TEXT,payload TEXT)"
            )
        repo = AreaRepository(database)
        repo.cache_air("Maharashtra", city, [{"city": city}])
        assert repo.query_air("Maharashtra", city)[0] == [{"city": city}]
        other = "Pune" if city == "Delhi" else "Delhi"
        assert repo.query_air("Maharashtra", other) == ([], None)


def test_native_copy_is_writable_and_keeps_cache_on_upgrade(tmp_path):
    bundle = ROOT / "assets"
    database = prepare_runtime(tmp_path, bundle)
    assert database.parent == tmp_path / "evidence"
    repo = AreaRepository(database)
    repo.cache_air("Delhi", "", [{"station": "Local cache"}])
    with sqlite3.connect(database) as db:
        manifest = json.loads(
            db.execute('SELECT value FROM metadata WHERE key="manifest"').fetchone()[0]
        )
        manifest["built_at"] = "old build"
        db.execute(
            'UPDATE metadata SET value=? WHERE key="manifest"', (json.dumps(manifest),)
        )
    assert prepare_runtime(tmp_path, bundle) == database
    assert AreaRepository(database).air_records()[0] == [{"station": "Local cache"}]


def test_native_python_https_paginates_and_redacts(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {"total": 2, "records": [{"station": str(len(seen))}]}
            ).encode()

    def open_(request, **kwargs):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(air_client, "urlopen", open_)
    assert (
        len(air_client.PythonAirClient("private-test-key").fetch_records("Delhi")) == 2
    )
    assert "offset=1" in seen[1]

    def broken(*a, **k):
        raise OSError("https://host/?api-key=private-test-key")

    monkeypatch.setattr(air_client, "urlopen", broken)
    with pytest.raises(air_client.FetchError) as error:
        air_client.PythonAirClient("private-test-key").fetch_records("Delhi")
    assert "private-test-key" not in str(error.value)


def test_packaging_has_no_credentials_or_heavy_build_dependencies():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    excluded = config["tool"]["flet"]["app"]["exclude"]
    assert ".env" in excluded and "data" in excluded and "tests" in excluded
    dependencies = config["project"]["dependencies"]
    assert not any(
        name in dep
        for dep in dependencies
        for name in ("osmium", "scikit-learn", "shapely", "scipy", "Flask")
    )
    with sqlite3.connect(ROOT / "assets" / "datasets" / "areas.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM air_cache").fetchone()[0] == 0
    assert not list((ROOT / "assets").rglob(".env"))


def test_cached_clusters_work_without_sklearn(service):
    assert service.clusters()["available"]
    before = service.results[0]["score"]
    service.clusters()
    assert service.results[0]["score"] == before


def test_browser_app_is_served_in_process_without_listener():
    from starlette.testclient import TestClient

    from server import app

    with TestClient(app) as browser:
        response = browser.get("/")
        assert response.status_code == 200
        assert "flutter" in response.text.lower()
        assert browser.get("/icon.svg").status_code == 200


def test_real_phone_width_browser_session():
    from starlette.testclient import TestClient

    from server import app

    with TestClient(app) as browser:
        with browser.websocket_connect("/ws") as socket:
            socket.send_bytes(
                b"\x00"
                + msgpack.packb(
                    [
                        1,
                        {
                            "session_id": "",
                            "page_name": "",
                            "page": {
                                "width": 390,
                                "height": 844,
                                "web": True,
                                "platform": "ios",
                                "route": "/",
                            },
                        },
                    ]
                )
            )
            greeting = msgpack.unpackb(socket.receive_bytes()[1:], raw=False)
            assert greeting[0] == 1 and not greeting[1]["error"]
            update = msgpack.unpackb(
                socket.receive_bytes()[1:],
                raw=False,
                strict_map_key=False,
                ext_hook=lambda code, value: value,
            )
            assert update[0] == 2
            rendered = str(update)
            assert "Your priorities" in rendered
            assert "Air quality (PM2.5)" in rendered
            assert "SESSION_CRASHED" not in rendered


def test_keys_and_preferences_are_session_local(service):
    first = LocalyticsApp(FakePage(), service)
    second = LocalyticsApp(FakePage(), LocalyticsService(DATA_DIR / "areas.sqlite"))
    first._session_key = "only-in-first-session"
    assert second.key() is None
    before = dict(second.service.selection.weights)
    first.service.apply(Selection(weights={"park": 5}))
    assert second.service.selection.weights == before
    assert b"only-in-first-session" not in first.service.csv_export()


def test_export_supplies_bytes_to_portable_save_dialog(service, monkeypatch):
    import flet as ft

    saved = []

    class Picker:
        async def save_file(self, **kwargs):
            saved.append(kwargs)
            return "export.csv"

    monkeypatch.setattr(ft, "FilePicker", Picker)
    ui = LocalyticsApp(FakePage(web=True), service)
    asyncio.run(ui.export())
    assert saved[0]["file_name"].endswith(".csv")
    assert saved[0]["src_bytes"].startswith(b"area_id,")


def test_search_inputs_have_bounded_responsive_widths(service):
    """Wrapping Rows give unconstrained TextFields a broken Flutter layout."""
    import flet as ft

    for width in (390, 1200):
        ui = LocalyticsApp(FakePage(width), service)
        ui.mount()
        for index in (1, 2):
            ui.navigate(SimpleNamespace(control=SimpleNamespace(selected_index=index)))
        search_sections = (
            (ui.sections[1], ((ui.state, ui.city),)),
            (
                ui.sections[2],
                (
                    (ui.transport_lat, ui.transport_lon),
                    (ui.transport_radius, ui.transport_limit),
                ),
            ),
        )
        for section, field_groups in search_sections:
            search_panel = section.controls[2]
            rows = search_panel.content.controls
            for index, fields in enumerate(field_groups):
                row = rows[index]
                assert isinstance(row, ft.ResponsiveRow)
                assert row.controls == list(fields)
                for field in fields:
                    assert not field.expand
                    assert field.col["xs"] == 12  # A bounded full-width phone field.
                    assert field.col["md"] == 6  # Two bounded columns on desktop.


def test_map_markers_use_supported_controls_and_keep_station_clicks(service):
    import flet as ft

    ui = LocalyticsApp(FakePage(), service)
    nearby, _ = service.nearby_transport(28.462786, 77.076088, radius=5, limit=5)
    facilities = [point for group in nearby.values() for point in group]
    assert facilities
    for point in facilities:
        marker = ui.marker(point["lat"], point["lon"], point["name"], "#2878b5")
        assert isinstance(marker.content, ft.Container)
        assert isinstance(marker.content.content, ft.Icon)
        assert marker.content.tooltip == point["name"]
        assert marker.width == marker.height == 30
        assert marker.coordinates.latitude == point["lat"]
        assert marker.coordinates.longitude == point["lon"]
    tapped = []
    marker = ui.marker(28.6, 77.2, "Air station", "#2878b5", lambda event: tapped.append(True))
    marker.content.on_click(None)
    assert tapped == [True]


def test_phone_grid_culling_preserves_all_ranked_cells(service):
    ui = LocalyticsApp(FakePage(390), service)
    ui.mount()
    assert ui.sections[1:] == [None, None, None]
    assert len(ui.polygon_layer.polygons) < len(service.cells) / 2
    assert len(service.results) == len(service.cells)
    initial = list(service.shortlist)
    ui._camera = (28.61, 77.20, 8)
    ui._map_size = (1200, 470)
    ui.render_grid()
    assert len(ui._visible_ids) == len(service.cells)
    assert service.shortlist == initial


def test_area_selection_reuses_grid_and_shortlist(service):
    ui = LocalyticsApp(FakePage(390), service)
    ui.mount()
    polygons = list(ui.polygon_layer.polygons)
    shortlist_controls = list(ui.ranking_list.controls)
    ui.select(ui._visible_ids[0])
    assert all(a is b for a, b in zip(polygons, ui.polygon_layer.polygons))
    assert all(a is b for a, b in zip(shortlist_controls, ui.ranking_list.controls))
    assert len(service.results) == 1487
    ui.toggle_compare(service.shortlist[0]["id"])
    assert all(a is b for a, b in zip(polygons, ui.polygon_layer.polygons))


def test_camera_updates_are_debounced_and_restore_cells(service):
    ui = LocalyticsApp(FakePage(390), service)
    ui.mount()
    updates = ui.page.updates
    def camera(lat):
        return SimpleNamespace(camera=SimpleNamespace(
            center=SimpleNamespace(latitude=lat, longitude=77.2), zoom=12,
        ))
    async def pan():
        await asyncio.gather(ui.map_position_changed(camera(28.62)),
                             ui.map_position_changed(camera(28.8)))
    asyncio.run(pan())
    assert ui.page.updates == updates + 1
    assert ui._camera[0] == 28.8
    west, south, east, north = ui.viewport_bounds()
    assert all(service.cells_by_id[id]["lat"] <= north + 0.02 for id in ui._visible_ids)
    assert ui._visible_ids


def test_shortlist_follows_map_and_details_are_bounded(service):
    for width in (390, 900, 1400):
        page = FakePage(width)
        ui = LocalyticsApp(page, service)
        ui.mount()
        if width >= 1200:
            assert ui.map_results.controls == [ui.area_map_panel]
            assert ui.area_layout.controls[-1] is ui.detail_card
            assert ui.detail_card.height == ui.area_map_panel.height == ui.preferences_card.height
        else:
            assert ui.map_results.controls == [ui.area_map_panel, ui.detail_expander]
            assert ui.detail_scroll.height == 360
            ui.select(service.shortlist[0]["id"])
            assert ui.detail_expander.expanded
        # Resizing must reparent the details without duplicating their controls.
        page.width = 390 if width >= 1200 else 1400
        ui.resize()
        assert sum(c is ui.detail_card for c in ui.area_layout.controls) == (page.width >= 1200)


def test_all_map_navigation_buttons_call_the_right_map(service, monkeypatch):
    from unittest.mock import AsyncMock
    import flet as ft

    ui = LocalyticsApp(FakePage(), service)
    for map_control, center, zoom in (
        (ui.area_map, (28.61, 77.20), 10),
        (ui.station_map, (22.5937, 78.9629), 5),
        (ui.transport_map, (28.61, 77.20), 10),
    ):
        for method in ("zoom_in", "zoom_out", "move_to"):
            monkeypatch.setattr(map_control, method, AsyncMock())
        stack = ui.map_with_controls(map_control, center, zoom)
        assert isinstance(stack, ft.Stack)
        assert stack.controls[0] is map_control
        buttons = stack.controls[1].content.controls
        for button in buttons:
            asyncio.run(button.on_click(None))
        map_control.zoom_in.assert_awaited_once()
        map_control.zoom_out.assert_awaited_once()
        destination = map_control.move_to.call_args.args[0]
        assert (destination.latitude, destination.longitude) == center
        assert map_control.move_to.call_args.kwargs == {"zoom": zoom, "rotation": 0}


def test_shortlist_and_footer_use_full_width_sections(service):
    import flet as ft

    ui = LocalyticsApp(FakePage(1400), service)
    ui.mount()
    section = ui.sections[0]
    assert section.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    position = section.controls.index(ui.area_layout)
    assert section.controls[position + 1] is ui.shortlist_panel
    assert ui.shortlist_panel not in ui.map_results.controls
    assert isinstance(ui.ranking_list, ft.ResponsiveRow)
    assert len(ui.ranking_list.controls) == 10
    assert all(card.col == {"xs": 12, "md": 6, "xl": 4} for card in ui.ranking_list.controls)
    assert ui.preferences_card.content.scroll == ft.ScrollMode.AUTO
    ui.page.width = 390
    ui.resize()
    assert ui.preferences_card.height is None
    assert ui.preferences_card.content.height is None


def test_compare_button_updates_and_dialog_removals_stay_in_sync(service):
    page = FakePage()
    dialogs = []
    page.show_dialog = dialogs.append
    page.pop_dialog = lambda: dialogs.pop()
    ui = LocalyticsApp(page, service)
    ui.mount()
    selected = service.shortlist[0]["id"]
    ui.select(selected)
    ui.compare_button.on_click(None)
    assert service.comparison == [selected]
    assert ui.compare_button.content == "Remove from comparison"
    assert ui.comparison_tray.visible
    assert "1/3 areas selected" in ui.message.value
    ui.open_comparison()
    assert len(dialogs) == 1
    rows = ui.comparison_dialog_content.controls[1].controls[0].rows
    assert len(rows) == 11
    assert len(rows[0].cells) == 2
    remove_button = ui.comparison_dialog_content.controls[-1].controls[0]
    remove_button.on_click(None)
    assert service.comparison == []
    assert not ui.comparison_tray.visible
    assert ui.compare_button.content == "Add to comparison"
    assert len(ui.comparison_dialog_content.controls) == 1
    dialogs[0].actions[0].on_click(None)
    assert not dialogs


def test_comparison_rejects_fourth_and_displays_three_columns(service):
    page = FakePage(390)
    dialogs = []
    page.show_dialog = dialogs.append
    ui = LocalyticsApp(page, service)
    ui.mount()
    for row in service.shortlist[:4]:
        ui.select(row["id"])
        ui.compare_button.on_click(None)
    assert len(service.comparison) == 3
    assert "three" in ui.message.value.lower()
    assert ui.compare_button.content == "Add to comparison"
    ui.open_comparison()
    table = ui.comparison_dialog_content.controls[1].controls[0]
    assert len(table.columns) == 4
    assert all(len(row.cells) == 4 for row in table.rows)
    assert ui.comparison_dialog_content.width == 310
