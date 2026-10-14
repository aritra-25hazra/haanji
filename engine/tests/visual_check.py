"""Screenshots and an axe-core run over the four demo pages.

Run by hand, against a server you started:

    python -m haanji.cli serve --port 8090 &
    python tests/visual_check.py

Not a pytest test: it needs a browser and a network for fonts.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("HAANJI_BASE", "http://127.0.0.1:8090")
OUT = os.environ.get("SHOTS", os.path.join(os.path.dirname(__file__), "..", "..", ".superpowers", "shots"))
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
PAGES = ["", "talk", "whatsapp", "verify"]
SIZES = {"desktop": (1440, 900), "mobile": (390, 844)}

os.makedirs(OUT, exist_ok=True)
problems = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    for label, (w, h) in SIZES.items():
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        page = ctx.new_page()
        for path in PAGES:
            name = (path or "landing") + "-" + label
            page.goto(f"{BASE}/{path}", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            if path == "":
                try:
                    page.wait_for_selector("#hero-call .stamp", timeout=25_000)
                except Exception:
                    problems.append(f"{name}: the hero never reached the stamp")
                # Walk down the page so every reveal-on-scroll section has fired,
                # then come back up: the full-page shot should show what a reader sees.
                page.evaluate("""async () => {
                    const h = document.documentElement.scrollHeight;
                    for (let y = 0; y < h; y += window.innerHeight * 0.6) {
                        window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
                    }
                    window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 400));
                }""")
            else:
                time.sleep(0.8)
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            if overflow:
                problems.append(f"{name}: horizontal overflow")
            page.add_script_tag(url=AXE)
            page.wait_for_function("window.axe !== undefined")
            result = page.evaluate("axe.run(document, {runOnly: ['wcag2a', 'wcag2aa']})")
            for v in result["violations"]:
                if v["impact"] in ("serious", "critical"):
                    targets = ", ".join(n["target"][0] for n in v["nodes"][:3])
                    problems.append(f"{name}: [{v['impact']}] {v['id']} — {v['help']} ({targets})")
            page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=(path == ""))
            print("shot", name)
        ctx.close()
    browser.close()

print()
if problems:
    print("PROBLEMS")
    for line in problems:
        print(" -", line)
    sys.exit(1)
print("all pages: no overflow, no serious/critical axe issues; screenshots in", OUT)
