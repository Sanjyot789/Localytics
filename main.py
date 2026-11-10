"""Python app entry point. Desktop: python main.py. Browser: python main.py --web."""

import argparse
import sqlite3

import flet as ft
from dotenv import load_dotenv

from config import ROOT
from native_app.runtime import prepare_runtime
from native_app.service import LocalyticsService
from native_app.ui import LocalyticsApp


async def main(page: ft.Page):
    load_dotenv(ROOT / ".env")  # Development/server only; .env is excluded from native builds.
    try:
        database = prepare_runtime()
        application = LocalyticsApp(page, LocalyticsService(database))
        application.mount()
    except (OSError, ValueError, sqlite3.Error):
        page.title = "Localytics"
        page.add(
            ft.SafeArea(
                ft.Column(
                    [
                        ft.Text("Localytics needs its evidence data", size=24),
                        ft.Text(
                            "Run python scripts/prepare_app.py before packaging, or restore data/areas.sqlite for local development."
                        ),
                    ]
                ),
                expand=True,
            )
        )


def launch():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", action="store_true", help="Run the Python-hosted browser version.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Use 0.0.0.0 only to allow devices on your network."
    )
    parser.add_argument("--port", type=int, default=8550)
    args = parser.parse_args()
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER if args.web else ft.AppView.FLET_APP,
        host=args.host,
        port=args.port,
        assets_dir=str(ROOT / "assets"),
    )


if __name__ == "__main__":
    launch()
