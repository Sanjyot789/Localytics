"""Python ASGI deployment: uvicorn server:app --host 0.0.0.0 --port 8550."""

import flet as ft

from config import ROOT
from main import main

app = ft.run(main, assets_dir=str(ROOT / "assets"), export_asgi_app=True)
