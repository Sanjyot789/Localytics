"""Responsive Flet interface. All controls, maps and event handlers are Python."""

import asyncio
import json
import math

import flet as ft
import flet_map as fm

from air_client import FetchError
from config import DEFAULTS, FACILITY_COLORS, FACTORS
from geography import coordinates, distance_km
from native_app.service import Selection, score_color
from observations import monitors, severity

TEAL = "#087F8C"
INK = "#15354C"
MUTED = "#536B7D"
BG = "#EFF4F8"


def note(value):
    return ft.Text(value, size=12, color=MUTED, selectable=True)


def title(value):
    return ft.Text(value, size=19, weight=ft.FontWeight.BOLD, color=INK)


def panel(*controls, **kwargs):
    return ft.Container(
        content=ft.Column(list(controls), spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=18,
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#DBE3EB"),
        border_radius=18,
        **kwargs,
    )


def number(value):
    return "Unavailable" if value is None else f"{value:.2f}"


def table(headers, rows):
    return ft.Row(
        [
            ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD)) for h in headers],
                rows=[
                    ft.DataRow(
                        cells=[ft.DataCell(ft.Text(str(v), selectable=True, size=12)) for v in row]
                    )
                    for row in rows
                ],
            )
        ],
        scroll=ft.ScrollMode.AUTO,
    )


class LocalyticsApp:
    def __init__(self, page, service):
        self.page = page
        self.service = service
        self.selected = None
        self.busy = False
        self.pick_work = False
        self._session_key = None
        self.station_rows = []
        self.transport_selection = None
        self.progress = ft.ProgressBar(visible=False, color=TEAL)
        self.message = ft.Text("", color=TEAL, selectable=True)
        self.weights = {}
        self.ratings = {}
        for key, label in FACTORS.items():
            rating = ft.Text(str(DEFAULTS.get(key, 0)), color=TEAL)

            def changed(event, key=key, rating=rating):
                rating.value = str(int(event.control.value))
                self.page.update()

            self.ratings[key] = rating
            self.weights[key] = ft.Slider(
                min=0,
                max=5,
                divisions=5,
                value=DEFAULTS.get(key, 0),
                label="{value}",
                on_change_end=changed,
            )
        self.radius = ft.Dropdown(
            label="Local search radius",
            value="2",
            options=[ft.DropdownOption(str(v), f"{v} km") for v in (1, 2, 5)],
        )
        self.cap = ft.Dropdown(
            label="Facility count cap",
            value="10",
            options=[ft.DropdownOption(str(v)) for v in (5, 10, 20)],
        )
        self.work_lat = ft.TextField(
            label="Workplace latitude", keyboard_type=ft.KeyboardType.NUMBER
        )
        self.work_lon = ft.TextField(
            label="Workplace longitude", keyboard_type=ft.KeyboardType.NUMBER
        )
        self.must = {
            c: ft.TextField(
                label=f"{label} within km (optional)", keyboard_type=ft.KeyboardType.NUMBER
            )
            for c, label in [
                ("metro_station", "Metro"),
                ("school", "School"),
                ("hospital", "Hospital"),
                ("park", "Public green space"),
                ("ev", "EV charging"),
            ]
        }
        self.map_mode = ft.Dropdown(
            label="Map colours",
            value="score",
            width=230,
            options=[
                ft.DropdownOption("score", "Suitability"),
                ft.DropdownOption("group", "Similar-area groups"),
            ],
            on_select=self.change_mode,
        )
        self.polygon_layer = fm.PolygonLayer(polygons=[], polygon_labels=False)
        self.air_layer = fm.CircleLayer(circles=[])
        self.nearby_layer = fm.MarkerLayer(markers=[])
        self.area_map = self.make_map(
            [self.polygon_layer, self.air_layer, self.nearby_layer], self.map_tap
        )
        self.details = ft.Column(
            [
                title("Select an area"),
                note(
                    "Tap a grid cell or a shortlist entry. Its scores, nearby services and air observations appear here."
                ),
            ],
            spacing=10,
        )
        self.ranking_list = ft.ResponsiveRow(spacing=12, run_spacing=12)
        self.comparison = ft.Column()
        self.comparison_tray = ft.Column(visible=False)
        self.compare_button = None
        self.comparison_dialog_content = None
        self.metrics = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=INK)
        self.air_summary = ft.Text("", color=MUTED)
        self.api_key = ft.TextField(
            label="Your data.gov.in API key (optional if configured on this computer/server)",
            password=True,
            can_reveal_password=True,
        )
        self.state = ft.TextField(
            label="State / union territory", hint_text="e.g. Maharashtra", col={"xs": 12, "md": 6}
        )
        self.city = ft.TextField(label="City (optional)", hint_text="e.g. Pune", col={"xs": 12, "md": 6})
        self.station_layer = fm.MarkerLayer(markers=[])
        self.station_map = self.make_map(
            [self.station_layer], self.station_tap, center=(22.5937, 78.9629), zoom=5
        )
        self.station_details = ft.Column(
            [note("Load a city, then tap a monitor or map point to inspect its readings.")]
        )
        self.station_summary = ft.Text("Search any city represented in the air-quality dataset.")
        self.transport_lat = ft.TextField(
            label="Latitude", keyboard_type=ft.KeyboardType.NUMBER, col={"xs": 12, "md": 6}
        )
        self.transport_lon = ft.TextField(
            label="Longitude", keyboard_type=ft.KeyboardType.NUMBER, col={"xs": 12, "md": 6}
        )
        self.transport_radius = ft.TextField(
            label="Radius in km", value="5", keyboard_type=ft.KeyboardType.NUMBER, col={"xs": 12, "md": 6}
        )
        self.transport_limit = ft.TextField(
            label="Results per type", value="5", keyboard_type=ft.KeyboardType.NUMBER, col={"xs": 12, "md": 6}
        )
        self.transport_layer = fm.MarkerLayer(markers=[])
        self.transport_map = self.make_map([self.transport_layer], self.transport_tap)
        self.transport_details = ft.Column(
            [note("Enter coordinates or tap the map to choose a location.")]
        )
        self._section_builders = [self.build_areas, self.build_air, self.build_transport, self.build_about]
        self.sections = [self.build_areas(), None, None, None]
        zoom = 12 if (self.page.width or 1200) < 700 else 10
        self.area_map.initial_zoom = zoom
        self._camera = (28.61, 77.20, zoom)
        self._map_size = None
        self._camera_revision = 0
        self._polygon_cache = {}
        self._visible_ids = ()
        self._cell_bounds = {}
        for cell in self.service.cells:
            polygons = cell["geometry"]["coordinates"]
            if cell["geometry"]["type"] != "MultiPolygon":
                polygons = [polygons]
            points = [point for polygon in polygons for point in polygon[0]]
            self._cell_bounds[cell["id"]] = (
                min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points),
            )
        self.area_map.on_position_change = self.map_position_changed
        self.area_map.on_size_change = self.map_size_changed
        self.body = ft.Column([self.sections[0]], expand=True, scroll=ft.ScrollMode.AUTO,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.navigation = ft.NavigationBar(
            selected_index=0,
            on_change=self.navigate,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.GRID_VIEW, label="Areas"),
                ft.NavigationBarDestination(icon=ft.Icons.AIR, label="Air quality"),
                ft.NavigationBarDestination(icon=ft.Icons.DIRECTIONS_TRANSIT, label="Transport"),
                ft.NavigationBarDestination(icon=ft.Icons.INFO_OUTLINE, label="About"),
            ],
        )
        self.refresh_views()

    def make_map(self, layers, on_tap, center=(28.61, 77.20), zoom=10):
        return fm.Map(
            initial_center=fm.MapLatitudeLongitude(*center),
            initial_zoom=zoom,
            min_zoom=3,
            max_zoom=18,
            height=360 if (self.page.width or 1200) < 700 else 470,
            on_tap=on_tap,
            layers=[
                fm.TileLayer(
                    url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    user_agent_package_name="org.localytics.app/1.0",
                ),
                *layers,
                fm.SimpleAttribution(text="OpenStreetMap contributors"),
            ],
        )

    def map_with_controls(self, map_control, center, zoom):
        async def zoom_in(event):
            await map_control.zoom_in()

        async def zoom_out(event):
            await map_control.zoom_out()

        async def reset(event):
            await map_control.move_to(
                fm.MapLatitudeLongitude(*center), zoom=zoom, rotation=0,
            )

        buttons = ft.Container(
            content=ft.Column([
                ft.IconButton(ft.Icons.ADD, tooltip="Zoom in", on_click=zoom_in),
                ft.IconButton(ft.Icons.REMOVE, tooltip="Zoom out", on_click=zoom_out),
                ft.IconButton(ft.Icons.HOME, tooltip="Reset map view", on_click=reset),
            ], spacing=0),
            top=10, right=10, bgcolor="#FFFFFF", border_radius=10,
            border=ft.Border.all(1, "#DBE3EB"),
        )
        return ft.Stack([map_control, buttons])

    def build_areas(self):
        factors = []
        for key, label in FACTORS.items():
            factors.extend(
                [
                    ft.Row(
                        [ft.Text(label, expand=True, weight=ft.FontWeight.BOLD), self.ratings[key]]
                    ),
                    self.weights[key],
                ]
            )
        preferences = ft.ExpansionTile(
            title=ft.Text("Your priorities"),
            subtitle=note("0 = ignore; 5 = very important"),
            expanded=True,
            controls=[
                ft.Column(
                    [
                        *factors,
                        note("PM2.5 is a relative indicator, not official AQI."),
                        self.radius,
                        self.cap,
                        ft.ExpansionTile(
                            title=ft.Text("Workplace / college"),
                            controls=[
                                self.work_lat,
                                self.work_lon,
                                ft.TextButton("Choose workplace on map", on_click=self.choose_work),
                            ],
                        ),
                        ft.ExpansionTile(
                            title=ft.Text("Must-have proximity"),
                            controls=[
                                *self.must.values(),
                                note(
                                    "Limits cannot exceed the local radius. School quality and EV connector suitability are unverified."
                                ),
                            ],
                        ),
                        ft.FilledButton(
                            "Update recommendations", on_click=self.apply, bgcolor=TEAL
                        ),
                    ],
                    spacing=8,
                )
            ],
        )
        self.preferences_panel = preferences
        pref_panel = panel(preferences, col={"xs": 12, "md": 4, "xl": 3})
        self.preferences_card = pref_panel
        map_panel = panel(
            title("Delhi area comparison"),
            self.metrics,
            self.map_mode,
            self.map_with_controls(self.area_map, (28.61, 77.20), 10),
            note(
                "Green: score >=70; amber: 40-69; red: <40; grey: missing evidence or unmet requirement."
            ),
            note(
                "Tap a cell. Changing priorities can change the shortlist. Group colours describe similarity, not quality."
            ),
        )
        shortlist_panel = panel(
            title("Your best matches"),
            note("Ranked by your priorities. Select an area to explore its evidence."),
            self.ranking_list,
            ft.Button("Export all scores as CSV", on_click=self.export),
        )
        self.detail_scroll = ft.Column([self.details], scroll=ft.ScrollMode.AUTO, height=560)
        self.detail_card = panel(self.detail_scroll)
        self.detail_expander = ft.ExpansionTile(
            title=ft.Text("Selected area details"), controls=[self.detail_card], expanded=False,
        )
        self.map_results = ft.Column(
            [map_panel], col={"xs": 12, "md": 8, "xl": 6}, spacing=14,
        )
        self.area_layout = ft.ResponsiveRow([pref_panel, self.map_results])
        self.shortlist_panel = shortlist_panel
        self.area_map_panel = map_panel
        return ft.Column(
            [
                ft.Container(
                    content=ft.Column([
                        ft.Text("LOCALYTICS  /  NEIGHBOURHOOD EXPLORER", size=11, color="#86D6D4", weight=ft.FontWeight.BOLD),
                        ft.Text("Find a place that fits your life.", size=27, color="#FFFFFF", weight=ft.FontWeight.BOLD),
                        ft.Text("Set your priorities. Explore Delhi. Compare your best matches.", size=14, color="#D9E9F1"),
                    ], spacing=8),
                    bgcolor=INK, padding=24, border_radius=20,
                ),
                self.comparison_tray,
                self.area_layout,
                self.shortlist_panel,
                ft.ResponsiveRow([
                    panel(title("Compare areas"), self.comparison, col=12),
                    panel(
                    title("Air-quality evidence"),
                    self.air_summary,
                    ft.Button("Refresh Delhi readings", on_click=self.refresh_delhi),
                    note(
                        "Nearby valid PM2.5 readings within 5 km and 6 hours inform the air indicator."
                    ),
                    col={"xs": 12, "md": 6},
                    ),
                ]),
                panel(
                    title("About the evidence"),
                    note(
                        "School quality, water, crime, affordability, density, routed commute times and residential land-use filtering need further evidence. They do not affect these rankings."
                    ),
                ),
            ],
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def build_air(self):
        return ft.Column(
            [
                title("Air quality across Indian cities"),
                note("Transport coverage does not restrict air-quality searches."),
                panel(
                    ft.ResponsiveRow([self.state, self.city]),
                    self.api_key,
                    ft.FilledButton("Load station data", on_click=self.load_stations, bgcolor=TEAL),
                    self.station_summary,
                ),
                self.map_with_controls(self.station_map, (22.5937, 78.9629), 5),
                panel(self.station_details),
                note("Reading colours are indicative PM2.5 bands, not official overall AQI."),
            ],
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def build_transport(self):
        return ft.Column(
            [
                title("Nearby transport"),
                note("Search the bundled OSM evidence without an Overpass request."),
                panel(
                    ft.ResponsiveRow([self.transport_lat, self.transport_lon]),
                    ft.ResponsiveRow([self.transport_radius, self.transport_limit]),
                    ft.FilledButton("Find transport", on_click=self.find_transport, bgcolor=TEAL),
                ),
                self.map_with_controls(self.transport_map, (28.61, 77.20), 10),
                panel(self.transport_details),
                note(
                    "Straight-line distances. Coverage and passenger airport service are not guaranteed."
                ),
            ],
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def build_about(self):
        manifest = self.service.manifest
        groups = self.service.clusters()
        evaluation = self.service.repository.read_report("evaluation_report.json")
        controls = [
            title("About Localytics"),
            note("Group 7 | Area suitability analytics"),
            panel(
                title("How the index works"),
                ft.Text(
                    "Each positive priority is divided by the sum of priorities. The index is 100 times the weighted sum of factor scores."
                ),
                note(
                    "Services: equal parts distance and nearby count. Daily transit averages bus and metro access. Airports use 25 km; workplace distance uses a 50 km cap."
                ),
                note(
                    "PM2.5 score = 1 - min(value/250, 1). The cap is a project choice, not a safe-air limit. Missing positive-weight evidence or an unmet must-have makes a cell unranked."
                ),
            ),
            panel(
                title("Evidence and coverage"),
                ft.Text(
                    f"{manifest['cell_count']:,} cells; boundary {manifest['boundary_area_km2']:.1f} km². Built {manifest['built_at']}"
                ),
                note(
                    " | ".join(
                        f"{k.replace('_', ' ')}: {v:,}" for k, v in manifest["counts"].items()
                    )
                ),
                *[note(v) for v in manifest["limitations"]],
            ),
        ]
        if groups.get("available"):
            controls.append(
                panel(
                    title("Similar-area groups"),
                    ft.Text(
                        f"{groups['method']} | {groups['k']} groups | silhouette {groups['silhouette']} | stability {groups['stability']}"
                    ),
                    note(
                        "Precomputed K-Means/hierarchical comparisons are reused by data version. Model-only median filling and scaling never enter user scores."
                    ),
                    table(
                        ["Method", "Groups", "Silhouette"],
                        [[r["method"], r["k"], r["silhouette"]] for r in groups["trials"]],
                    ),
                    ft.Button("Export clustering report", on_click=self.export_clusters),
                )
            )
        else:
            controls.append(
                panel(
                    title("Similar-area groups"),
                    note(groups.get("reason", "No valid clustering report.")),
                )
            )
        if evaluation:
            controls.append(
                panel(
                    title("Ranking sensitivity checks"),
                    note(
                        "These are offline descriptive comparisons, not measured user relevance or prediction accuracy."
                    ),
                    table(
                        ["Scenario", "Eligible cells", "Top-ten overlap"],
                        [
                            [r["scenario"], r["eligible"], f"{r['top10_overlap_with_default']:.0%}"]
                            for r in evaluation["ranking_scenarios"]
                        ],
                    ),
                    ft.Button("Export evaluation report", on_click=self.export_evaluation),
                )
            )
        controls.append(
            panel(
                title("Sources"),
                ft.Text(
                    "Facilities: © OpenStreetMap contributors (ODbL). Boundary: DataMeet, CC BY-SA 2.5 India. Air: data.gov.in / CPCB."
                ),
                note(
                    "Maps need internet for tiles. Offline recommendations use the local database. New cells are not evidence of residential suitability."
                ),
                note(
                    "The application interface and analytics are written in Python. Flet/Flutter supplies the underlying platform renderer."
                ),
            )
        )
        return ft.Column(controls, spacing=14)

    def mount(self):
        self.page.title = "Localytics"
        self.page.bgcolor = BG
        self.page.padding = 14
        self.page.theme = ft.Theme(color_scheme_seed=TEAL)
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.appbar = ft.AppBar(
            title=ft.Text("Localytics", weight=ft.FontWeight.BOLD, color="#FFFFFF"), bgcolor=INK
        )
        self.page.navigation_bar = self.navigation
        self.page.on_resize = self.resize
        self.page.add(
            ft.SafeArea(
                ft.Column([self.progress, self.message, self.body], expand=True), expand=True
            )
        )
        self.resize()

    def resize(self, event=None):
        narrow = (self.page.width or 1200) < 700
        self.preferences_panel.expanded = not narrow
        dashboard_height = (360 if narrow else 470) + 260
        self.preferences_card.height = None if narrow else dashboard_height
        self.preferences_card.content.height = None if narrow else dashboard_height - 36
        self.preferences_card.content.scroll = None if narrow else ft.ScrollMode.AUTO
        self.area_map_panel.height = None if narrow else dashboard_height
        sidebar = (self.page.width or 1200) >= 1200
        pref_panel = self.area_layout.controls[0]
        if sidebar:
            self.map_results.controls = [self.area_map_panel]
            self.detail_expander.controls = []
            self.detail_card.col = {"xs": 12, "xl": 3}
            self.area_layout.controls = [pref_panel, self.map_results, self.detail_card]
            self.detail_scroll.height = dashboard_height - 36
            self.detail_card.height = dashboard_height
        else:
            self.area_layout.controls = [pref_panel, self.map_results]
            self.detail_expander.controls = [self.detail_card]
            self.map_results.controls = [self.area_map_panel, self.detail_expander]
            self.detail_scroll.height = 360
            self.detail_card.height = None
        for map_control in (self.area_map, self.station_map, self.transport_map):
            map_control.height = 360 if narrow else 470
        self.render_grid()
        self.page.update()

    def navigate(self, event):
        index = event.control.selected_index
        if index != 0:
            lat, lon, zoom = self._camera
            self.area_map.initial_center = fm.MapLatitudeLongitude(lat, lon)
            self.area_map.initial_zoom = zoom
        if self.sections[index] is None:
            self.sections[index] = self._section_builders[index]()
        self.body.controls = [self.sections[index]]
        self.page.update()

    def notice(self, text, error=False):
        self.message.value = text
        self.message.color = "#B94058" if error else TEAL
        self.page.update()

    async def job(self, operation, success):
        if self.busy:
            return
        self.busy = True
        self.progress.visible = True
        self.page.update()
        try:
            value = await asyncio.to_thread(operation)
            await success(value)
        except (FetchError, ValueError, OSError) as exc:
            self.notice(str(exc), True)
        finally:
            self.busy = False
            self.progress.visible = False
            self.page.update()

    async def apply(self, event=None):
        try:
            work = None
            if self.work_lat.value or self.work_lon.value:
                work = coordinates(self.work_lat.value, self.work_lon.value)
            must = {
                key: float(control.value) for key, control in self.must.items() if control.value
            }
            selection = Selection(
                {k: int(v.value) for k, v in self.weights.items()},
                int(self.radius.value),
                int(self.cap.value),
                work,
                must,
            )
            selection.validate()
        except (ValueError, TypeError) as exc:
            self.notice(str(exc), True)
            return

        async def finished(_):
            self.refresh_views()
            self.notice("Recommendations updated.")

        await self.job(lambda: self.service.apply(selection), finished)

    def choose_work(self, event=None):
        self.pick_work = True
        self.notice("Tap the area map to choose your workplace, then update recommendations.")

    def map_tap(self, event):
        lat, lon = event.coordinates.latitude, event.coordinates.longitude
        if self.pick_work:
            self.work_lat.value = f"{lat:.6f}"
            self.work_lon.value = f"{lon:.6f}"
            self.pick_work = False
            self.notice("Workplace selected. Set Workplace distance above zero to include it.")
            return
        result = self.service.select_at(lat, lon)
        if result:
            self.select(result["id"])
        else:
            self.notice(
                "That point is outside the Delhi recommendation grid. Air-quality searches for other cities are available on the Air quality tab."
            )

    def viewport_bounds(self):
        lat, lon, zoom = self._camera
        width, height = self._map_size or (max(self.page.width or 1200, 200), self.area_map.height)
        world = 256 * 2 ** zoom
        x = (lon + 180) / 360 * world
        latitude = math.radians(max(-85, min(85, lat)))
        y = (1 - math.asinh(math.tan(latitude)) / math.pi) / 2 * world
        # Overscan keeps cells visible while a camera update travels over Wi-Fi.
        dx, dy = width * 0.65, height * 0.65
        def longitude(px):
            return px / world * 360 - 180

        def latitude_at(py):
            return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / world))))
        return longitude(x-dx), latitude_at(y+dy), longitude(x+dx), latitude_at(y-dy)

    def render_grid(self):
        west, south, east, north = self.viewport_bounds()
        visible = [cell for cell in self.service.cells if (
            self._cell_bounds[cell["id"]][0] <= east and self._cell_bounds[cell["id"]][2] >= west
            and self._cell_bounds[cell["id"]][1] <= north and self._cell_bounds[cell["id"]][3] >= south
        )]
        groups = self.service.clusters() if self.map_mode.value == "group" else None
        if groups and not groups.get("available"):
            self.map_mode.value = "score"
            groups = None
        colours = ["#A8AFB7", "#4178BE", "#975BB5", "#D87E22", "#2B9A70", "#CE5577", "#6C7627"]
        for cell in visible:
            cell_id = cell["id"]
            if cell_id not in self._polygon_cache:
                polygons = cell["geometry"]["coordinates"]
                if cell["geometry"]["type"] != "MultiPolygon":
                    polygons = [polygons]
                self._polygon_cache[cell_id] = [fm.PolygonMarker(
                    coordinates=[fm.MapLatitudeLongitude(lat, lon) for lon, lat in polygon[0]],
                ) for polygon in polygons]
            color = (colours[groups["labels"].get(cell_id, 0) % len(colours)]
                     if groups else score_color(self.service.by_id[cell_id]["score"]))
            for polygon in self._polygon_cache[cell_id]:
                polygon.color = ft.Colors.with_opacity(0.55, color)
                polygon.border_color = INK if cell_id == self.selected else "#FFFFFF"
                polygon.border_stroke_width = 2 if cell_id == self.selected else 0.6
        ids = tuple(cell["id"] for cell in visible)
        if ids != self._visible_ids:
            self.polygon_layer.polygons = [p for cell_id in ids for p in self._polygon_cache[cell_id]]
            self._visible_ids = ids

    async def map_position_changed(self, event):
        self._camera = (event.camera.center.latitude, event.camera.center.longitude, event.camera.zoom)
        self._camera_revision += 1
        revision = self._camera_revision
        await asyncio.sleep(0.18)
        if revision == self._camera_revision:
            self.render_grid()
            self.page.update()

    def map_size_changed(self, event):
        if event.width > 0 and event.height > 0:
            self._map_size = (event.width, event.height)
            self.render_grid()
            self.page.update()

    def refresh_views(self):
        self.render_grid()
        self.air_layer.circles = [
            fm.CircleMarker(
                radius=5,
                coordinates=fm.MapLatitudeLongitude(s["lat"], s["lon"]),
                color=severity(s["pm"])["color"],
                border_color=INK,
                border_stroke_width=1,
            )
            for s in self.service.stations
        ]
        eligible = sum(r["score"] is not None for r in self.service.results)
        self.metrics.value = f"{len(self.service.cells):,} cells · {eligible:,} ranked · {len(self.service.cells) - eligible:,} unranked"
        self.air_summary.value = f"{len(self.service.air_rows)} cached readings; last fetched: {self.service.air_fetched or 'not yet'}."
        self.ranking_list.controls = []
        for index, r in enumerate(self.service.shortlist, 1):
            contributions = sorted(r["contributions"].items(), key=lambda kv: kv[1], reverse=True)[
                :3
            ]
            self.ranking_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Text(f"{index:02d}", color=TEAL, weight=ft.FontWeight.BOLD),
                            bgcolor="#E2F3F2", padding=10, border_radius=10,
                        ),
                        ft.Column([
                            ft.Text(r["label"], size=14, weight=ft.FontWeight.BOLD, color=INK),
                            note(" · ".join(FACTORS[k] for k, _ in contributions)),
                        ], expand=True, spacing=6),
                        ft.Container(
                            content=ft.Text(f"{r['score']:.1f}", size=18, color=TEAL, weight=ft.FontWeight.BOLD),
                            bgcolor="#E2F3F2", padding=10, border_radius=10,
                        ),
                    ], spacing=10),
                    col={"xs": 12, "md": 6, "xl": 4},
                    bgcolor="#F6F9FC", border=ft.Border.all(1, "#DFE8EF"),
                    border_radius=14, padding=14,
                    on_click=lambda e, id=r["id"]: self.select(id),
                )
            )
        if not self.ranking_list.controls:
            self.ranking_list.controls = [
                note(
                    "No verified match with the selected factors and requirements. Adjust priorities or refresh missing air data. Observations remain visible on the map."
                )
            ]
        self.render_comparison()
        if self.selected:
            self.render_details(self.service.by_id[self.selected])

    def change_mode(self, event=None):
        self.render_grid()
        self.page.update()

    def select(self, cell_id):
        self.selected = cell_id
        if (self.page.width or 1200) < 1200:
            self.detail_expander.expanded = True
        self.render_grid()
        self.render_details(self.service.by_id[cell_id])
        self.notice("Area selected. Details and nearest facilities are shown with the map.")

    def render_details(self, r):
        self.nearby_layer.markers = []
        for category, f in r["features"].items():
            for p in f["nearby"]:
                self.nearby_layer.markers.append(
                    self.marker(p["lat"], p["lon"], p["name"], FACILITY_COLORS[category])
                )
        self.compare_button = ft.Button(
            "Remove from comparison" if r["id"] in self.service.comparison else "Add to comparison",
            on_click=lambda e, cell_id=r["id"]: self.toggle_compare(cell_id),
            color=TEAL,
        )
        controls = [
            title(r["label"]),
            note(f"{r['id']} · {r['lat']:.5f}, {r['lon']:.5f}"),
            ft.Text(
                "Unranked" if r["score"] is None else f"{r['score']:.1f} / 100",
                size=28,
                weight=ft.FontWeight.BOLD,
                color=TEAL,
            ),
            self.compare_button,
        ]
        if r["missing"]:
            controls.append(
                note("Missing selected factors: " + ", ".join(FACTORS[k] for k in r["missing"]))
            )
        if r["checks"]:
            controls.append(note(" | ".join(f"{c['factor']}: {c['status']}" for c in r["checks"])))
        controls.append(
            table(
                ["Factor", "Score /100", "Contribution"],
                [
                    [
                        label,
                        number(
                            r["scores"].get(k) * 100 if r["scores"].get(k) is not None else None
                        ),
                        number(r["contributions"].get(k))
                        if self.service.selection.weights.get(k, 0) > 0
                        else "Ignored",
                    ]
                    for k, label in FACTORS.items()
                ],
            )
        )
        controls.extend(self.air_detail(r["air"]))
        for category, f in r["features"].items():
            children = [
                note(
                    f"Nearest: {number(f['nearest_km'])} km. Extent: {'covered' if f['coverage'] else 'partial / unavailable'}."
                ),
                *[
                    note(f"{p['name']} · {p['km']:.2f} km · {p['method']} · access {p['access']}")
                    for p in f["nearby"]
                ],
            ]
            controls.append(
                ft.ExpansionTile(
                    title=ft.Text(f"{category.replace('_', ' ')} · {f['count']} nearby"),
                    controls=children,
                )
            )
        controls.append(
            note(
                "Up to five nearest facilities per type are marked. Current availability and service quality are unverified."
            )
        )
        self.details.controls = controls

    def air_detail(self, air):
        controls = [title("Air-quality observations")]
        if air:
            controls.extend(
                [
                    ft.Text(f"{air['name']} · {air['distance_km']} km away"),
                    note(f"PM2.5: {air['pm']} · observation age: {air['age_hours']} hours"),
                    note(air["status"]),
                    self.reading_table(air["readings"]),
                ]
            )
            if air.get("scoring_monitor"):
                controls.append(
                    note(f"Ranking monitor: {air['scoring_monitor']}; input {air['scoring_value']}")
                )
        else:
            controls.append(
                note("No cached readings. Refresh Delhi readings to load monitoring evidence.")
            )
        return controls

    def toggle_compare(self, cell_id):
        try:
            removing = cell_id in self.service.comparison
            self.service.compare(cell_id)
            self.render_comparison()
            if self.compare_button is not None and self.selected:
                self.compare_button.content = (
                    "Remove from comparison" if self.selected in self.service.comparison
                    else "Add to comparison"
                )
            label = self.service.by_id[cell_id]["label"]
            self.notice(f"{label} {'removed' if removing else 'added'}. {len(self.service.comparison)}/3 areas selected. Use View comparison to compare scores.")
        except ValueError as exc:
            self.notice(str(exc), True)

    def comparison_controls(self):
        rows = [self.service.by_id[id] for id in self.service.comparison]
        if not rows:
            return [note("Select a map cell or a best match, then press Add to comparison. You can compare up to three areas.")]
        values = [["Suitability /100", *[number(r["score"]) for r in rows]]]
        values.extend([
            [label, *[number(r["scores"].get(k) * 100 if r["scores"].get(k) is not None else None) for r in rows]]
            for k, label in FACTORS.items()
        ])
        return [
            note(f"{len(rows)}/3 areas selected. Factor scores are out of 100; higher is better. These are suitability indicators, not official AQI."),
            table(["Factor", *[r["label"] for r in rows]], values),
            ft.Row([
                ft.TextButton("Remove " + r["label"], on_click=lambda e, id=r["id"]: self.toggle_compare(id))
                for r in rows
            ], wrap=True),
        ]

    def render_comparison(self):
        self.comparison.controls = self.comparison_controls()
        count = len(self.service.comparison)
        self.comparison_tray.visible = count > 0
        self.comparison_tray.controls = [panel(
            ft.Row([
                ft.Text(f"{count}/3 areas selected", weight=ft.FontWeight.BOLD, color=TEAL, expand=True),
                ft.FilledButton("View comparison", on_click=self.open_comparison, bgcolor=TEAL),
            ]),
            note(" · ".join(self.service.by_id[id]["label"] for id in self.service.comparison)),
        )]
        if self.comparison_dialog_content is not None:
            self.comparison_dialog_content.controls = self.comparison_controls()

    def open_comparison(self, event=None):
        if not self.service.comparison:
            self.notice("Add at least one area from its details panel first.", True)
            return
        self.comparison_dialog_content = ft.Column(
            self.comparison_controls(), scroll=ft.ScrollMode.AUTO,
            height=440, width=max(240, min(1050, (self.page.width or 1200) - 80)),
        )
        dialog = ft.AlertDialog(
            title="Compare selected areas",
            content=self.comparison_dialog_content,
            actions=[ft.TextButton("Close", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    def key(self):
        return (self.api_key.value or "").strip() or self._session_key or None

    async def refresh_delhi(self, event=None):
        key = self.key()

        async def finished(rows):
            if key:
                self._session_key = key
                self.api_key.value = ""
            self.refresh_views()
            self.notice(f"Refreshed {len(rows)} Delhi readings.")

        await self.job(lambda: self.service.refresh("Delhi", "", key), finished)

    async def load_stations(self, event=None):
        state = (self.state.value or "").strip()
        city = (self.city.value or "").strip()
        key = self.key()

        async def finished(rows):
            self.station_rows = rows
            if key:
                self._session_key = key
                self.api_key.value = ""
            stations = monitors(rows)
            self.station_layer.markers = [
                self.marker(
                    s["lat"],
                    s["lon"],
                    s["name"],
                    severity(s["pm"])["color"],
                    lambda e, s=s: self.show_station(s),
                )
                for s in stations
            ]
            self.station_summary.value = f"{len(rows)} readings · {len(stations)} stations. No results? Leave City blank to check available stations."
            if state.casefold() == "delhi":
                self.refresh_views()
            if stations:
                await self.station_map.move_to(
                    fm.MapLatitudeLongitude(stations[0]["lat"], stations[0]["lon"]), zoom=10
                )
                self.show_station(stations[0])
            self.notice(
                "Station search complete. Transport coverage does not affect these readings."
            )

        await self.job(lambda: self.service.refresh(state, city, key), finished)

    def station_tap(self, event):
        stations = monitors(self.station_rows)
        if stations:
            nearest = min(
                stations,
                key=lambda s: distance_km(
                    event.coordinates.latitude, event.coordinates.longitude, s["lat"], s["lon"]
                ),
            )
            self.show_station(nearest)

    def show_station(self, s):
        self.station_details.controls = [
            title(s["name"]),
            note(f"PM2.5: {s['pm']} · {s['stamp'] or 'Unknown time'}"),
            self.reading_table(s["readings"]),
        ]
        self.page.update()

    def reading_table(self, rows):
        return table(
            ["Pollutant", "Min", "Max", "Average", "Updated"],
            [
                [
                    r.get(k, "NA")
                    for k in ["pollutant_id", "min_value", "max_value", "avg_value", "last_update"]
                ]
                for r in rows
            ],
        )

    def marker(self, lat, lon, label, color, on_click=None):
        return fm.Marker(
            coordinates=fm.MapLatitudeLongitude(lat, lon),
            content=ft.Container(
                content=ft.Icon(ft.Icons.LOCATION_ON, color=color, size=25),
                width=30,
                height=30,
                alignment=ft.Alignment.CENTER,
                tooltip=label,
                on_click=on_click,
            ),
            width=30,
            height=30,
        )

    def transport_tap(self, event):
        self.transport_lat.value = f"{event.coordinates.latitude:.6f}"
        self.transport_lon.value = f"{event.coordinates.longitude:.6f}"
        self.notice("Transport location selected. Press Find transport to search.")

    async def find_transport(self, event=None):
        try:
            lat, lon = coordinates(self.transport_lat.value, self.transport_lon.value)
            radius = float(self.transport_radius.value)
            limit = int(self.transport_limit.value)
        except (ValueError, TypeError):
            self.notice("Enter valid coordinates, radius and result count.", True)
            return

        async def finished(value):
            results, covered = value
            self.transport_layer.markers = [
                self.marker(p["lat"], p["lon"], p["name"], FACILITY_COLORS[k])
                for k, rows in results.items()
                for p in rows
            ]
            self.transport_details.controls = [
                note(
                    "Search radius is within extract bounds; completeness is not guaranteed."
                    if covered
                    else "Coverage unavailable or partial. Empty results do not prove no transport exists."
                )
            ]
            for category, rows in results.items():
                self.transport_details.controls.extend(
                    [
                        title(category.replace("_", " ").title()),
                        *(
                            [ft.Text(f"{p['name']} · {p['distance_km']:.2f} km") for p in rows]
                            or [note("No mapped matches.")]
                        ),
                    ]
                )
            await self.transport_map.move_to(fm.MapLatitudeLongitude(lat, lon), zoom=12)
            self.notice("Nearby transport loaded.")

        await self.job(lambda: self.service.nearby_transport(lat, lon, radius, limit), finished)

    async def save(self, name, content):
        try:
            result = await ft.FilePicker().save_file(file_name=name, src_bytes=content)
            self.notice(
                "Export handed to your browser/device save dialog."
                if self.page.web
                else ("Export saved." if result else "Export cancelled.")
            )
        except Exception:
            self.notice(
                "The save dialog is unavailable on this device. Try the browser version or another save location.",
                True,
            )

    async def export(self, event=None):
        await self.save("localytics_areas.csv", self.service.csv_export())

    async def export_clusters(self, event=None):
        await self.save(
            "localytics_clusters.json", json.dumps(self.service.clusters(), indent=2).encode()
        )

    async def export_evaluation(self, event=None):
        await self.save(
            "localytics_evaluation.json",
            json.dumps(
                self.service.repository.read_report("evaluation_report.json"), indent=2
            ).encode(),
        )
