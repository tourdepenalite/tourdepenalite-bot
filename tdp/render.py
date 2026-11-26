"""HTML -> JPEG (le seul format image accepte par l'API Instagram)."""
from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright


def render(htmls: list[str], out_dir: pathlib.Path, prefix: str) -> list[pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        exe = os.environ.get("TDP_CHROME")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for i, html in enumerate(htmls, 1):
            h = 1920 if "height:1920px" in html else 1350
            pg = b.new_page(viewport={"width": 1080, "height": h})
            pg.set_content(html)
            pg.wait_for_timeout(120)
            path = out_dir / f"{prefix}_{i:02d}.jpg"
            pg.screenshot(path=str(path), type="jpeg", quality=92)
            pg.close()
            paths.append(path)
        b.close()
    return paths
