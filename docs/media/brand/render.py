"""Render docs/media/brand/banner.html to docs/media/banner.png (the README header).

    engine/.venv/bin/python docs/media/brand/render.py

Needs Playwright with Chromium (pip install playwright; playwright install chromium).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "banner.png"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 400}, device_scale_factor=2)
    page.goto((HERE / "banner.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(OUT))
    browser.close()
print(f"wrote {OUT.relative_to(HERE.parents[2])}")
