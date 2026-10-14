# Signboard Demo Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the engine's four demo pages (`/`, `/talk`, `/whatsapp`, `/verify`) with a distinctive "Signboard" design — shared design system, painted-repair and stamp signature components, a scripted hero call on the landing page, and a live engine panel beside the `/talk` transcript — and make them work on the live Render + Vercel hosts.

**Architecture:** Plain HTML/CSS/JS served by the existing FastAPI demo server from `engine/haanji/web/`. One stylesheet (`signboard.css`) holds tokens and components; one script (`signboard.js`) holds shared behaviours and exposes a `Signboard` global; each page keeps its own layout CSS and page logic inline. The server gains three small things (console URL in status, correct MIME types, phonetic keys on corrections). Structure is pinned by FastAPI `TestClient` tests in `engine/tests/test_web.py`; look and accessibility are checked with a Playwright + axe script run by hand.

**Tech Stack:** Python 3.11, FastAPI, pytest + `fastapi.testclient`; HTML5, CSS custom properties, Web Animations API, IntersectionObserver, Web Speech API; Google Fonts (Bricolage Grotesque, Yatra One, Instrument Sans, JetBrains Mono); Playwright (Python) + axe-core for the visual pass; GitHub Actions for keep-awake.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-14-demo-pages-redesign-design.md` — every token, copy string and behaviour below comes from it.
- Pages never use raw hex; all colours come from the CSS custom properties in `signboard.css`.
- **All URLs in the four pages and their scripts are relative** (`api/status`, `static/signboard.css`, `talk`), never root-relative, so the same files work at `/talk` and at `/engine/talk` through the Vercel rewrite. External `https://` links are the only exception.
- **No emoji anywhere in the interface.** Icons are inline SVG from the `Signboard.icon()` set (Lucide-style, 1.75 px stroke). Text characters like `→ · —` are fine; dingbats like `✓ ✔ ✘` are not (use the `check`/`x` icons).
- Body text ≥ 16 px; chips 13 px; every control ≥ 44 px tall; `touch-action: manipulation` on buttons; visible 3 px marigold focus ring; `prefers-reduced-motion` honoured.
- Copy is sentence case. Buttons say what happens: "Start call", "Call khatam karo", "Bhejo". No developer messages ("run `haanji serve`") or `localhost` on any page.
- Motion tokens: `--t-micro: 160ms`, `--t-base: 240ms`, `--t-paint: 400ms`, `--ease-out: cubic-bezier(.2,.8,.2,1)`, `--ease-in: cubic-bezier(.4,0,1,1)`.
- Git: use `/Library/Developer/CommandLineTools/usr/bin/git` (the `git` on PATH is blocked by the Xcode licence shim). Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Python for engine work: `/private/tmp/claude-501/-Users-aritrahazra-Desktop-Antigravity-1-Major-Project-1-haanji/6017372c-e708-41b5-a18a-b2457744c449/scratchpad/venv/bin/python` (3.11, engine installed with `[dev]`). Call it `$PY` below. Run pytest from `engine/`.
- The hero script, pillar numbers and transcript lines are the README's real figures: `31.6% → 1.1%`, `239 → 137 ms`, `45.5%`, `80 / 80`, receipt `2504-7863`.

---

## File map

| Path | Responsibility |
|---|---|
| `engine/haanji/server.py` | `api/status` adds `console_url`; `static/{name}` MIME by extension; corrections carry `key`/`to_key`. Nothing else changes. |
| `engine/tests/test_web.py` | **New.** TestClient tests for the server changes and for every page's structure and the two global rules (no emoji, relative URLs). |
| `engine/haanji/web/signboard.css` | **New.** Tokens, base, and components: wordmark, nav, btn, chip, repair, stamp, frame, card, bubble, typing, wave, input, reveal, wall, badge, reduced-motion. |
| `engine/haanji/web/signboard.js` | **New.** `window.Signboard = { REDUCED, icon, mountIcons, reveal, paintRepair, stamp, typingDots, timer, waveform, status, esc, repairNode }`. |
| `engine/haanji/web/hero-call.js` | **New.** The landing hero's scripted call loop. |
| `engine/haanji/web/index.html` | **Rewritten.** Landing page. |
| `engine/haanji/web/talk.html` | **Rewritten.** Call + engine panel. |
| `engine/haanji/web/whatsapp.html` | **Rewritten.** WhatsApp simulator in Signboard chrome. |
| `engine/haanji/web/verify.html` | **Rewritten.** Verifier with stamp verdict and chain strip. |
| `engine/tests/visual_check.py` | **New.** Playwright screenshots + axe run (not collected by pytest). |
| `console/src/App.tsx`, `console/src/pages/PackStudio.tsx` | Links to `/engine/talk`, `/engine/whatsapp`. |
| `console/nginx.conf` | `location /engine/` proxy. |
| `render.yaml` | `HAANJI_CONSOLE_URL`. |
| `.github/workflows/keep-awake.yml` | **New.** 10-minute ping. |

---

### Task 1: Server — console URL, MIME types, phonetic keys

**Files:**
- Modify: `engine/haanji/server.py` (imports ~line 30; `_turn_payload` ~line 130; `status` ~line 414; `static_file` ~line 445)
- Test: `engine/tests/test_web.py` (new)

**Interfaces:**
- Produces: `GET api/status` → `{..., "console_url": str}`; `GET static/<name>` → media type `text/css` / `text/javascript` / `image/svg+xml` / `text/plain`; each item of a turn's `corrections` → `{from_token, to_surface, asr_confidence, key, to_key}`.

- [ ] **Step 1: Write the failing tests**

Create `engine/tests/test_web.py`:

```python
"""The demo server's pages and the small contracts the pages rely on."""
import os
import re

import pytest
from fastapi.testclient import TestClient

from haanji.server import app

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "haanji", "web")
PAGES = {"/": "index.html", "/talk": "talk.html", "/whatsapp": "whatsapp.html", "/verify": "verify.html"}


@pytest.fixture
def client():
    return TestClient(app)


def test_status_exposes_the_console_url(client, monkeypatch):
    monkeypatch.delenv("HAANJI_CONSOLE_URL", raising=False)
    assert client.get("/api/status").json()["console_url"] == "http://localhost:5173"
    monkeypatch.setenv("HAANJI_CONSOLE_URL", "https://haanji-kappa.vercel.app")
    assert client.get("/api/status").json()["console_url"] == "https://haanji-kappa.vercel.app"


def test_static_files_are_served_with_their_media_type(client):
    assert client.get("/static/verifier.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/static/signboard.css").headers["content-type"].startswith("text/css")


def test_a_correction_carries_the_sound_keys_that_justified_it(client):
    sid = client.post("/api/sessions", json={"pack": "dental_clinic"}).json()["session_id"]
    turn = client.post(f"/api/sessions/{sid}/utterance",
                       json={"text": "haan ji mujhe rut kanal karwana tha"}).json()
    [c] = turn["corrections"]
    assert c["from_token"] == "rut kanal" and c["to_surface"] == "root canal"
    assert c["key"] and c["key"] == c["to_key"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd engine && $PY -m pytest tests/test_web.py -v`
Expected: 3 FAILED — `KeyError: 'console_url'`, content-type `application/javascript` / 404 for the css, `KeyError: 'key'`.

- [ ] **Step 3: Implement the three server changes**

In `engine/haanji/server.py`, add the import after `from .backend.local import LocalBackend`:

```python
from .bhasha.phonetics import phrase_key
```

In `_turn_payload`, replace the `"corrections"` entry:

```python
        "corrections": [{"from_token": c.from_token, "to_surface": c.to_surface,
                         "asr_confidence": c.asr_confidence,
                         "key": phrase_key(c.from_token), "to_key": phrase_key(c.to_surface)}
                        for c in record.corrections],
```

Replace the `status` route:

```python
@app.get("/api/status")
async def status():
    return {"name": "HaanJi demo server", "version": app.version,
            "default_pack": DEFAULT_PACK, "packs": list_packs(),
            "var_dir": VAR_DIR,
            # Where the owner console lives, so the pages can link to it
            # without hard-coding a host.
            "console_url": os.environ.get("HAANJI_CONSOLE_URL", "http://localhost:5173")}
```

Replace the body of `static_file` after the existence check:

```python
    media = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
             ".html": "text/html"}.get(os.path.splitext(name)[1], "text/plain")
    return FileResponse(path, media_type=media)
```

Create an empty-for-now stylesheet so the media-type test has a file to fetch — `engine/haanji/web/signboard.css` containing one line: `/* HaanJi — Signboard design system */`. Task 2 fills it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd engine && $PY -m pytest tests/test_web.py -v`
Expected: 3 passed.

Run: `cd engine && $PY -m pytest -q`
Expected: 164 passed (161 + 3).

- [ ] **Step 5: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/server.py engine/tests/test_web.py engine/haanji/web/signboard.css docs/superpowers/specs/2026-10-14-demo-pages-redesign-design.md
$G commit -q -F - <<'MSG'
feat(engine): small server contracts the new demo pages rely on

api/status now carries console_url (HAANJI_CONSOLE_URL, default the local
Vite port) so the pages can link to the owner console on any host; static
files are served with a media type from their extension instead of
text/plain for everything but .js; and every correction in a turn carries
the sound keys of the heard and corrected text, which is the evidence the
Bhasha panel shows.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 2: Design system — `signboard.css` and `signboard.js`

**Files:**
- Create: `engine/haanji/web/signboard.css` (replace the placeholder)
- Create: `engine/haanji/web/signboard.js`
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Produces (CSS): custom properties `--cobalt --cobalt-deep --marigold --chalk --ink --haze --sindoor --leaf --font-display --font-dev --font-body --font-mono --t-micro --t-base --t-paint --ease-out --ease-in --r-ctl --r-card --maxw --frame`; classes `.skip .wrap .dev .lead .mono .muted .eyebrow .badge .wordmark(.paint) .nav .btn(.btn-primary .btn-ghost .btn-danger .btn-icon) .chip(.chip-spec .chip-guard .chip-tool .chip-rcpt) .repair(.in) .stamp(.leaf) .frame .card .wall .section .grid-3 .row .stack .transcript .bubble(.agent .caller) .meta .typing .sys .wave .field .input(.input-pill) .ic .ic-sm [data-reveal](.in) .chain .ok`.
- Produces (JS): `window.Signboard` with
  `REDUCED: boolean`,
  `icon(name: string, cls?: string): string` (SVG markup),
  `mountIcons(root?: Element): void` (fills every `[data-icon]`),
  `reveal(): void`,
  `paintRepair(el: HTMLElement): Promise<void>`,
  `stamp(el: HTMLElement): Promise<void>`,
  `typingDots(): HTMLElement`,
  `timer(el: HTMLElement): {start(), stop(), reset()}`,
  `waveform(container: HTMLElement, bars?: number): {attach(analyser), detach(), setLive(bool), stop()}`,
  `status(): Promise<{packs, default_pack, console_url} | null>`,
  `esc(s: unknown): string`,
  `repairNode(c: {from_token, to_surface, asr_confidence?}): HTMLElement`.
  Icon names: `phone mic micOff speaker speakerOff bolt shield lock arrow check x chevron send phoneMissed github`.
  On `DOMContentLoaded` it runs `mountIcons()` and `reveal()`.

- [ ] **Step 1: Write the failing tests**

Append to `engine/tests/test_web.py`:

```python
TOKENS = ["--cobalt:", "--cobalt-deep:", "--marigold:", "--chalk:", "--ink:", "--haze:",
          "--sindoor:", "--leaf:", "--t-micro:", "--t-base:", "--t-paint:", "--ease-out:"]


def test_the_design_system_defines_every_token(client):
    css = client.get("/static/signboard.css").text
    for token in TOKENS:
        assert token in css, token
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css


def test_the_shared_script_exposes_the_signboard_api(client):
    js = client.get("/static/signboard.js").text
    for name in ["icon", "mountIcons", "reveal", "paintRepair", "stamp", "typingDots",
                 "timer", "waveform", "status", "esc", "repairNode"]:
        assert name in js, name
    assert 'fetch("api/status")' in js            # relative, never root-relative
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k "design_system or shared_script"`
Expected: 2 FAILED (tokens missing; 404 for signboard.js).

- [ ] **Step 3: Write `signboard.css`**

Replace `engine/haanji/web/signboard.css` with:

```css
/* HaanJi — Signboard design system.
   Loaded by every page the demo server serves. Pages use these tokens and
   components; they never write a raw hex colour. */

:root {
  --cobalt: #1B3B8C;
  --cobalt-deep: #102A66;
  --marigold: #F5B91E;
  --chalk: #FFF7E6;
  --ink: #14213D;
  --haze: #9FB3E8;
  --sindoor: #E2553A;
  --leaf: #8FD694;

  --font-display: "Bricolage Grotesque", "Arial Black", Impact, sans-serif;
  --font-dev: "Yatra One", "Tiro Devanagari Hindi", serif;
  --font-body: "Instrument Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;

  --t-micro: 160ms;
  --t-base: 240ms;
  --t-paint: 400ms;
  --ease-out: cubic-bezier(.2, .8, .2, 1);
  --ease-in: cubic-bezier(.4, 0, 1, 1);

  --r-ctl: 8px;
  --r-card: 14px;
  --maxw: 1180px;
  /* The double rule a signwriter paints around a board. */
  --frame: inset 0 0 0 4px var(--marigold), inset 0 0 0 7px var(--cobalt), inset 0 0 0 8px var(--marigold);
}

/* ── base ─────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; min-height: 100dvh;
  background: var(--cobalt); color: var(--chalk);
  font: 16px/1.5 var(--font-body);
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; }
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; touch-action: manipulation; }
:focus-visible { outline: 3px solid var(--marigold); outline-offset: 2px; border-radius: 4px; }
code { font-family: var(--font-mono); font-size: .92em; background: rgba(255, 247, 230, .1); padding: 1px 6px; border-radius: 5px; }
.wall code { background: rgba(27, 59, 140, .1); }

.skip { position: absolute; left: -999px; top: 8px; z-index: 100; background: var(--marigold); color: var(--cobalt); padding: 10px 14px; border-radius: var(--r-ctl); font-weight: 600; }
.skip:focus { left: 8px; }

.wrap { max-width: var(--maxw); margin: 0 auto; padding: 0 24px; }
.section { padding: 96px 0; }
@media (max-width: 700px) { .section { padding: 56px 0; } }

h1, h2, h3 { margin: 0; font-family: var(--font-display); font-weight: 800; line-height: 1.02; letter-spacing: -.02em; }
h1 { font-size: clamp(40px, 6vw, 80px); }
h2 { font-size: clamp(28px, 4vw, 56px); }
h3 { font-size: 22px; letter-spacing: -.01em; line-height: 1.15; }
p { margin: 0; }
.dev { font-family: var(--font-dev); font-weight: 400; color: var(--marigold); letter-spacing: 0; }
.lead { font-size: 18px; opacity: .9; max-width: 56ch; }
.mono { font-family: var(--font-mono); font-weight: 500; }
.muted { color: var(--haze); }
.ok { color: var(--leaf); }
.eyebrow { display: block; font-size: 13px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--marigold); margin-bottom: 12px; }
.badge { display: inline-block; padding: 4px 10px; border: 2px solid currentColor; border-radius: 4px; font-family: var(--font-display); font-weight: 800; font-size: 13px; letter-spacing: .1em; text-transform: uppercase; transform: rotate(-1.5deg); }

.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.stack { display: flex; flex-direction: column; gap: 12px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
@media (max-width: 800px) { .grid-3 { grid-template-columns: 1fr; } }

/* The whitewashed wall under the board: light sections. */
.wall { background: var(--chalk); color: var(--ink); }
.wall .dev { color: var(--cobalt); }
.wall .muted { color: rgba(20, 33, 61, .65); }
.wall .eyebrow { color: var(--cobalt); }
.wall .chip { background: rgba(27, 59, 140, .1); color: var(--cobalt); }
.wall .ok { color: #2E8B57; }

/* ── icons ────────────────────────────────────────────────────────────── */
.ic { width: 20px; height: 20px; flex: none; }
.ic-sm { width: 16px; height: 16px; flex: none; }
[data-icon] { display: inline-flex; line-height: 0; vertical-align: middle; }

/* ── wordmark & nav ───────────────────────────────────────────────────── */
.wordmark { display: inline-flex; align-items: baseline; gap: 10px; font-family: var(--font-display); font-weight: 800; font-size: 26px; letter-spacing: -.02em; color: var(--marigold); text-decoration: none; white-space: nowrap; }
.wordmark .dev { font-size: 22px; color: var(--chalk); }
.wordmark.paint { clip-path: inset(0 100% 0 0); animation: paint 600ms var(--ease-out) forwards; }
@keyframes paint { to { clip-path: inset(0 0 0 0); } }

.nav { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 72px; padding: 12px 0; }
.nav ul { display: flex; gap: 4px; list-style: none; margin: 0; padding: 0; flex-wrap: wrap; }
.nav ul a { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: var(--r-ctl); text-decoration: none; font-weight: 500; opacity: .85; transition: background var(--t-micro), opacity var(--t-micro); }
.nav ul a:hover { background: rgba(255, 247, 230, .08); opacity: 1; }

/* ── buttons ──────────────────────────────────────────────────────────── */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 0 20px; border-radius: var(--r-ctl); border: 1.5px solid transparent; font-weight: 600; text-decoration: none; background: transparent; transition: transform var(--t-micro) var(--ease-out), background var(--t-micro), border-color var(--t-micro), opacity var(--t-micro); }
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .45; cursor: default; transform: none; }
.btn-primary { background: var(--marigold); color: var(--cobalt); }
.btn-primary:hover:not(:disabled) { background: #FFC83D; }
.btn-ghost { border-color: rgba(255, 247, 230, .5); color: var(--chalk); }
.btn-ghost:hover:not(:disabled) { border-color: var(--chalk); }
.btn-danger { background: var(--sindoor); color: var(--chalk); }
.btn-icon { width: 44px; padding: 0; }
.btn .ic { width: 20px; height: 20px; }

/* ── chips ────────────────────────────────────────────────────────────── */
.chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 999px; font-size: 13px; font-weight: 600; background: rgba(245, 185, 30, .16); color: var(--marigold); white-space: nowrap; }
.chip .ic, .chip svg { width: 14px; height: 14px; }
.chip-spec { background: rgba(143, 214, 148, .16); color: var(--leaf); }
.chip-guard { background: rgba(226, 85, 58, .2); color: #FFB3A3; }
.chip-tool { background: rgba(255, 247, 230, .1); color: var(--chalk); }
.chip-rcpt { font-family: var(--font-mono); }

/* ── painted repair ───────────────────────────────────────────────────── */
.repair { display: inline-flex; flex-wrap: wrap; align-items: baseline; gap: 8px; font-size: 15px; }
.repair s { position: relative; text-decoration: none; color: var(--haze); padding: 0 2px; }
.repair s svg.stroke { position: absolute; left: -3px; top: 0; width: calc(100% + 6px); height: 100%; overflow: visible; pointer-events: none; }
.repair s svg.stroke path { stroke: var(--marigold); stroke-width: 3; fill: none; stroke-linecap: round; }
.repair b { color: var(--marigold); font-weight: 600; opacity: 0; transform: translateY(4px); transition: opacity var(--t-base) var(--ease-out) 80ms, transform var(--t-base) var(--ease-out) 80ms; }
.repair.in b { opacity: 1; transform: none; }
.repair small { font-family: var(--font-mono); font-size: 12px; color: var(--haze); }
.bubble.caller .repair s { color: rgba(27, 59, 140, .55); }
.bubble.caller .repair b { color: var(--cobalt); }
.bubble.caller .repair small { color: rgba(27, 59, 140, .7); }
.bubble.caller .repair s svg.stroke path { stroke: var(--cobalt); }

/* ── stamp ────────────────────────────────────────────────────────────── */
.stamp { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border: 2px solid var(--sindoor); border-radius: 6px; background: var(--chalk); color: var(--sindoor); font-family: var(--font-mono); font-weight: 500; font-size: 13px; letter-spacing: .06em; transform: rotate(-3deg); }
.stamp.leaf { border-color: #2E8B57; color: #2E8B57; }
.stamp .ic { width: 16px; height: 16px; }

/* ── surfaces ─────────────────────────────────────────────────────────── */
.frame { box-shadow: var(--frame); border-radius: var(--r-card); background: var(--cobalt-deep); padding: 24px; }
.card { background: var(--cobalt-deep); border-radius: var(--r-card); padding: 24px; }
a.frame, a.card { display: block; text-decoration: none; transition: transform var(--t-micro) var(--ease-out), box-shadow var(--t-micro); }
a.frame:hover { transform: translateY(-2px); }

/* ── transcript ───────────────────────────────────────────────────────── */
.transcript { display: flex; flex-direction: column; gap: 10px; }
.bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; font-size: 15px; line-height: 1.45; animation: bubble var(--t-base) var(--ease-out) both; }
.bubble.agent { align-self: flex-start; background: rgba(255, 247, 230, .1); border-bottom-left-radius: 4px; }
.bubble.caller { align-self: flex-end; background: var(--marigold); color: var(--cobalt); border-bottom-right-radius: 4px; }
.bubble .meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
@keyframes bubble { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.typing { display: inline-flex; gap: 4px; padding: 12px 14px; background: rgba(255, 247, 230, .1); border-radius: 14px; border-bottom-left-radius: 4px; align-self: flex-start; }
.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--haze); animation: blink 900ms infinite; }
.typing i:nth-child(2) { animation-delay: 150ms; }
.typing i:nth-child(3) { animation-delay: 300ms; }
@keyframes blink { 0%, 80%, 100% { opacity: .3; } 40% { opacity: 1; } }
.sys { align-self: center; text-align: center; font-size: 13px; color: var(--haze); }

/* ── waveform ─────────────────────────────────────────────────────────── */
.wave { display: flex; gap: 3px; align-items: center; height: 28px; }
.wave i { width: 3px; height: 4px; background: var(--marigold); border-radius: 2px; transition: height 80ms linear; }

/* ── chain ────────────────────────────────────────────────────────────── */
.chain { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chain i { position: relative; width: 34px; height: 14px; background: var(--marigold); border-radius: 3px; }
.chain i + i::before { content: ""; position: absolute; left: -6px; top: 6px; width: 6px; height: 2px; background: var(--marigold); }
.chain i.empty { background: transparent; border: 2px dashed rgba(245, 185, 30, .5); }
.chain i.bad { background: var(--sindoor); }
.chain i.bad::before { background: transparent; border-top: 2px dashed var(--sindoor); height: 0; }

/* ── controls ─────────────────────────────────────────────────────────── */
.field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--haze); }
.input { min-height: 44px; padding: 0 12px; border-radius: var(--r-ctl); border: 1.5px solid rgba(255, 247, 230, .3); background: var(--cobalt-deep); color: var(--chalk); }
.input::placeholder { color: var(--haze); }
.input-pill { border-radius: 999px; flex: 1; min-width: 0; }

/* ── reveal ───────────────────────────────────────────────────────────── */
[data-reveal] { opacity: 0; transform: translateY(12px); transition: opacity var(--t-base) var(--ease-out) calc(var(--i, 0) * 40ms), transform var(--t-base) var(--ease-out) calc(var(--i, 0) * 40ms); }
[data-reveal].in { opacity: 1; transform: none; }

/* ── reduced motion ───────────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition-duration: 1ms !important; }
  .wordmark.paint { clip-path: none; animation: none; }
  [data-reveal] { opacity: 1; transform: none; }
  .repair b { opacity: 1; transform: none; }
  .typing i { animation: none; opacity: .6; }
}
```

- [ ] **Step 4: Write `signboard.js`**

Create `engine/haanji/web/signboard.js`:

```js
/* HaanJi — shared behaviours for the Signboard pages. Plain ES2020, no build.
   Everything hangs off window.Signboard; pages call what they need. */
(function (global) {
  "use strict";

  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // One icon family (Lucide-style strokes). Inline SVG so colour follows the text.
  const PHONE = '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6.2 6.2l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>';
  const ICONS = {
    phone: PHONE,
    phoneMissed: '<line x1="23" y1="1" x2="17" y2="7"/><line x1="17" y1="1" x2="23" y2="7"/>' + PHONE,
    mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
    micOff: '<line x1="2" y1="2" x2="22" y2="22"/><path d="M18.9 13.4A7 7 0 0 0 19 12v-2"/><path d="M5 10v2a7 7 0 0 0 12 5"/><path d="M15 9.3V5a3 3 0 0 0-5.9-.7"/><path d="M9 9v3a3 3 0 0 0 5.1 2.1"/><line x1="12" y1="19" x2="12" y2="22"/>',
    speaker: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/>',
    speakerOff: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>',
    bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    chevron: '<polyline points="6 9 12 15 18 9"/>',
    send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    github: '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.3 6.4-1.5 6.4-7A5.4 5.4 0 0 0 20 4.8 5 5 0 0 0 19.9 1S18.7.7 16 2.5a13.4 13.4 0 0 0-7 0C6.3.7 5.1 1 5.1 1A5 5 0 0 0 5 4.8a5.4 5.4 0 0 0-1.5 3.8c0 5.4 3.3 6.6 6.4 7a3.4 3.4 0 0 0-.9 2.6V22"/>',
  };

  function icon(name, cls) {
    return '<svg class="' + (cls || "ic") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (ICONS[name] || "") + "</svg>";
  }

  function mountIcons(root) {
    (root || document).querySelectorAll("[data-icon]").forEach(function (el) {
      el.innerHTML = icon(el.dataset.icon, el.classList.contains("ic-sm") ? "ic-sm" : "ic");
    });
  }

  function reveal() {
    const els = document.querySelectorAll("[data-reveal]");
    if (REDUCED || !("IntersectionObserver" in window)) { els.forEach(function (e) { e.classList.add("in"); }); return; }
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.15 });
    els.forEach(function (e) { io.observe(e); });
  }

  // Painted repair: a brush stroke is drawn through the struck word; the CSS
  // then lets the corrected word fade in once .in is set.
  function paintRepair(el) {
    const s = el.querySelector("s");
    if (!s) { el.classList.add("in"); return Promise.resolve(); }
    let svg = s.querySelector("svg.stroke");
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "stroke");
      svg.setAttribute("viewBox", "0 0 100 10");
      svg.setAttribute("preserveAspectRatio", "none");
      svg.setAttribute("aria-hidden", "true");
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", "M1 6 Q 25 3, 50 6 T 99 5");      // a slightly wobbly hand stroke
      svg.appendChild(p);
      s.appendChild(svg);
    }
    const path = svg.querySelector("path");
    el.classList.add("in");
    if (REDUCED) { path.style.strokeDasharray = ""; path.style.strokeDashoffset = "0"; return Promise.resolve(); }
    const len = 120;
    path.style.strokeDasharray = String(len);
    path.style.strokeDashoffset = String(len);
    const anim = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return anim.finished.catch(function () {});
  }

  // A rubber stamp landing: big and faint, then down with a short dip at contact.
  function stamp(el) {
    el.style.opacity = "";
    if (REDUCED) return Promise.resolve();
    const a = el.animate([
      { transform: "rotate(-3deg) scale(1.35)", opacity: 0 },
      { opacity: 1, offset: 0.6 },
      { opacity: 0.8, offset: 0.7 },
      { transform: "rotate(-3deg) scale(1)", opacity: 1 },
    ], { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return a.finished.catch(function () {});
  }

  function typingDots() {
    const d = document.createElement("div");
    d.className = "typing";
    d.setAttribute("aria-hidden", "true");
    d.innerHTML = "<i></i><i></i><i></i>";
    return d;
  }

  function timer(el) {
    let t0 = 0, id = null;
    function tick() {
      const s = Math.floor((Date.now() - t0) / 1000);
      el.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }
    return {
      start: function () { t0 = Date.now(); tick(); clearInterval(id); id = setInterval(tick, 1000); },
      stop: function () { clearInterval(id); id = null; },
      reset: function () { this.stop(); el.textContent = "00:00"; },
    };
  }

  // Twelve bars. With an AnalyserNode they follow the mic; without one they
  // idle at a gentle pattern while live and rest flat otherwise.
  function waveform(container, bars) {
    container.innerHTML = "";
    const n = bars || 12, els = [];
    for (let i = 0; i < n; i++) { const b = document.createElement("i"); container.appendChild(b); els.push(b); }
    let analyser = null, buf = null, live = false, phase = 0, raf = null;
    function frame() {
      if (analyser) {
        analyser.getByteTimeDomainData(buf);
        const step = Math.floor(buf.length / n);
        for (let i = 0; i < n; i++) {
          let peak = 0;
          for (let j = i * step; j < (i + 1) * step; j++) peak = Math.max(peak, Math.abs(buf[j] - 128));
          els[i].style.height = Math.max(4, Math.min(28, peak / 128 * 60)) + "px";
        }
      } else if (live && !REDUCED) {
        phase += 0.18;
        for (let i = 0; i < n; i++) els[i].style.height = (8 + 10 * Math.abs(Math.sin(phase + i * 0.6))) + "px";
      } else {
        for (let i = 0; i < n; i++) els[i].style.height = "4px";
      }
      raf = requestAnimationFrame(frame);
    }
    frame();
    return {
      attach: function (a) { analyser = a; buf = new Uint8Array(a.fftSize); },
      detach: function () { analyser = null; },
      setLive: function (v) { live = !!v; },
      stop: function () { cancelAnimationFrame(raf); },
    };
  }

  let statusCache = null;
  function status() {
    if (!statusCache) {
      statusCache = fetch("api/status").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }
    return statusCache;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function repairNode(c) {
    const el = document.createElement("span");
    el.className = "repair";
    el.innerHTML = '<s aria-label="suna: ' + esc(c.from_token) + '">' + esc(c.from_token) + "</s>" +
      '<b aria-label="padha: ' + esc(c.to_surface) + '">' + esc(c.to_surface) + "</b>" +
      (c.asr_confidence != null ? "<small>" + Number(c.asr_confidence).toFixed(2) + "</small>" : "");
    return el;
  }

  global.Signboard = { REDUCED: REDUCED, icon: icon, mountIcons: mountIcons, reveal: reveal,
    paintRepair: paintRepair, stamp: stamp, typingDots: typingDots, timer: timer,
    waveform: waveform, status: status, esc: esc, repairNode: repairNode };

  document.addEventListener("DOMContentLoaded", function () { mountIcons(); reveal(); });
})(window);
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd engine && $PY -m pytest tests/test_web.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/web/signboard.css engine/haanji/web/signboard.js engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(web): the Signboard design system

Tokens, base styles and the components every demo page shares, in one
stylesheet; and the shared behaviours — icon set, scroll reveal, the painted
repair and rubber stamp animations, typing dots, a call timer, a mic
waveform and a cached status fetch — behind one Signboard global.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 3: Landing page — `index.html` and `hero-call.js`

**Files:**
- Create: `engine/haanji/web/hero-call.js`
- Rewrite: `engine/haanji/web/index.html`
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Consumes: `Signboard.{repairNode, paintRepair, stamp, typingDots, timer, icon, esc, status, REDUCED}` from Task 2; `api/status.console_url` from Task 1.
- Produces: the element ids `hero-call`, `pillars`, `console-link`, `w-bhasha` that the tests and visual check look for.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/test_web.py`:

```python
def test_the_landing_page_has_its_hero_pillars_and_links(client):
    html = client.get("/").text
    assert "Phone uthata hai." in html and "सबूत" in html
    assert 'id="hero-call"' in html and 'id="pillars"' in html
    for href in ('href="talk"', 'href="whatsapp"', 'href="verify"'):
        assert href in html, href
    assert 'href="static/signboard.css"' in html and 'src="static/hero-call.js"' in html
    assert "31.6% → 1.1%" in html and "239 → 137 ms" in html and "80 / 80" in html
    assert "localhost" not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k landing`
Expected: FAIL (old page has none of these).

- [ ] **Step 3: Write `hero-call.js`**

Create `engine/haanji/web/hero-call.js`:

```js
/* The landing hero: one real call from the README, replayed on a loop. */
(function () {
  "use strict";
  const S = window.Signboard;
  const root = document.getElementById("hero-call");
  if (!root || !S) return;

  const SCRIPT = [
    { who: "agent", text: "Haanji, Smile Care Dental. Main aapki kya madad karun?" },
    { who: "caller", text: "haan ji mujhe rut kanal karwana tha",
      repair: { from_token: "rut kanal", to_surface: "root canal", asr_confidence: 0.32 } },
    { who: "agent", text: "Theek hai. Kis din ka time dekhun?", ms: 22 },
    { who: "caller", text: "kal subah ka time mil jayega",
      chip: { kind: "spec", text: "check_availability — pehle se taiyaar" } },
    { who: "agent", text: "Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath. Ya phir subah saade 10 baje. Chalega?", ms: 31 },
    { who: "caller", text: "haan confirm kar do", chip: { kind: "tool", text: "book_appointment" } },
    { who: "agent", text: "Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath. Confirmation code 2504-7863.",
      stamp: "RECEIPT 2504-7863" },
  ];
  const GAP = 900, TYPING = 500, HOLD = 2500;

  const log = root.querySelector(".transcript");
  const tm = S.timer(root.querySelector(".timer"));
  let paused = false;
  root.addEventListener("mouseenter", function () { paused = true; });
  root.addEventListener("mouseleave", function () { paused = false; });
  root.addEventListener("focusin", function () { paused = true; });
  root.addEventListener("focusout", function () { paused = false; });

  const sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  async function wait(ms) { await sleep(ms); while (paused) await sleep(120); }

  function bubble(line) {
    const b = document.createElement("div");
    b.className = "bubble " + line.who;
    b.textContent = line.text;
    const meta = document.createElement("div");
    meta.className = "meta";
    if (line.repair) meta.appendChild(S.repairNode(line.repair));
    if (line.chip) {
      const c = document.createElement("span");
      c.className = "chip chip-" + line.chip.kind;
      c.innerHTML = (line.chip.kind === "spec" ? S.icon("bolt") : "") + S.esc(line.chip.text);
      meta.appendChild(c);
    }
    if (line.ms) { const m = document.createElement("span"); m.className = "mono muted"; m.textContent = line.ms + " ms"; meta.appendChild(m); }
    if (line.stamp) { const st = document.createElement("span"); st.className = "stamp"; st.textContent = line.stamp; st.style.opacity = "0"; meta.appendChild(st); }
    if (meta.children.length) b.appendChild(meta);
    return b;
  }

  function renderStatic() {
    SCRIPT.forEach(function (l) {
      const b = bubble(l);
      log.appendChild(b);
      b.querySelectorAll(".repair").forEach(function (r) { r.classList.add("in"); });
      b.querySelectorAll(".stamp").forEach(function (s) { s.style.opacity = ""; });
    });
    root.querySelector(".timer").textContent = "00:41";
  }

  async function play() {
    for (;;) {
      log.innerHTML = "";
      tm.start();
      for (const line of SCRIPT) {
        if (line.who === "agent") { const t = S.typingDots(); log.appendChild(t); log.scrollTop = log.scrollHeight; await wait(TYPING); t.remove(); }
        const b = bubble(line);
        log.appendChild(b);
        log.scrollTop = log.scrollHeight;
        const r = b.querySelector(".repair");
        if (r) { await wait(350); await S.paintRepair(r); }
        const st = b.querySelector(".stamp");
        if (st) { await wait(300); await S.stamp(st); }
        await wait(GAP);
      }
      tm.stop();
      await wait(HOLD);
      const fade = log.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: "cubic-bezier(.4,0,1,1)" });
      await fade.finished.catch(function () {});
      fade.cancel();
    }
  }

  if (S.REDUCED) renderStatic(); else play();
})();
```

- [ ] **Step 4: Write `index.html`**

Replace `engine/haanji/web/index.html` with:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HaanJi — AI receptionist jo Hinglish mein phone uthata hai</title>
<meta name="description" content="Clinic, salon ya lab ke liye AI voice receptionist. Har call uthata hai, booking likhta hai, aur saabit kar sakta hai ki caller ne kya haan boli.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Yatra+One&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/signboard.css">
<style>
  .hero { display: grid; grid-template-columns: 1.1fr 1fr; gap: 48px; align-items: center; padding: 32px 24px 96px; }
  .hero-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 22px; }
  .hero-copy .chip { height: 32px; }
  .phone { min-height: 440px; display: flex; flex-direction: column; gap: 14px; }
  .phone-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; letter-spacing: .1em; color: var(--marigold); }
  .phone-head .live { display: inline-flex; align-items: center; gap: 8px; }
  .phone-head .live i { width: 8px; height: 8px; border-radius: 50%; background: var(--leaf); box-shadow: 0 0 0 4px rgba(143, 214, 148, .25); }
  .phone .transcript { flex: 1; max-height: 420px; overflow: hidden; }
  @media (max-width: 900px) { .hero { grid-template-columns: 1fr; padding-bottom: 56px; } .phone { min-height: 360px; } }

  .pillars { margin-top: 36px; }
  .pillar { display: flex; flex-direction: column; align-items: flex-start; gap: 14px; padding: 28px; border-radius: var(--r-card); background: rgba(255, 247, 230, .55); border: 1px solid rgba(27, 59, 140, .12); }
  .pillar .badge { color: var(--cobalt); }
  .pillar .num { display: flex; flex-direction: column; gap: 2px; }
  .pillar .num b { font-family: var(--font-display); font-weight: 800; font-size: 32px; letter-spacing: -.02em; color: var(--cobalt); }
  .pillar .num span { font-size: 13px; color: rgba(20, 33, 61, .7); }
  .widget { width: 100%; margin-top: 4px; min-height: 36px; }
  .widget .repair s { color: rgba(20, 33, 61, .45); }
  .widget .repair b { color: var(--cobalt); }
  .widget .repair s svg.stroke path { stroke: var(--cobalt); }
  .widget .repair small { color: rgba(20, 33, 61, .6); }
  .bars { display: flex; flex-direction: column; gap: 8px; }
  .bars div { display: grid; grid-template-columns: 44px 1fr 36px; align-items: center; gap: 8px; font-size: 13px; }
  .bars i { display: block; height: 10px; width: 0; border-radius: 5px; background: var(--cobalt); transition: width 600ms var(--ease-out) 200ms; }
  .in .bars i { width: var(--w); }
  .bars div:last-child i { background: #2E8B57; }
  .bars em { font-style: normal; font-family: var(--font-mono); font-size: 12px; text-align: right; }
  .widget.chain i { background: var(--cobalt); }
  .widget.chain i + i::before { background: var(--cobalt); }
  .widget.chain i.bad { background: var(--cobalt); transition: background 300ms var(--ease-out) 700ms; }
  .in .widget.chain i.bad { background: var(--sindoor); }
  .widget.chain i.bad::before { border-top-color: var(--cobalt); transition: border-color 300ms 700ms; }
  .in .widget.chain i.bad::before { border-top-color: var(--sindoor); }

  .try { display: flex; flex-direction: column; gap: 10px; min-height: 220px; color: var(--chalk); }
  .try .eyebrow { margin: 0; }
  .try p { color: var(--haze); font-size: 15px; }
  .try .go { margin-top: auto; align-self: flex-end; color: var(--marigold); }
  .open h3 { margin-bottom: 10px; }
  .open p { color: rgba(20, 33, 61, .78); }
  .open a { color: var(--cobalt); }
  .foot { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; padding: 28px 24px; border-top: 1px solid rgba(255, 247, 230, .15); font-size: 14px; }
  .foot a { color: var(--marigold); }
</style>
</head>
<body>
<a class="skip" href="#main">Seedha content pe jao</a>
<header class="wrap">
  <nav class="nav" aria-label="Main">
    <a class="wordmark paint" href="./">HaanJi <span class="dev">हाँजी</span></a>
    <ul>
      <li><a href="talk">Demo</a></li>
      <li><a href="whatsapp">WhatsApp</a></li>
      <li><a href="verify">Verify</a></li>
      <li><a href="https://github.com/aritra-25hazra/haanji" rel="noopener"><i data-icon="github" class="ic-sm"></i>GitHub</a></li>
      <li id="console-li" hidden><a id="console-link" href="#" rel="noopener">Console <i data-icon="arrow" class="ic-sm"></i></a></li>
    </ul>
  </nav>
</header>

<main id="main">
  <section class="hero wrap">
    <div class="hero-copy">
      <span class="chip" data-reveal>AI receptionist · Hinglish</span>
      <h1 data-reveal style="--i:1">Phone uthata hai.<br>Hinglish mein.<br><span class="dev">सबूत</span> ke saath.</h1>
      <p class="lead" data-reveal style="--i:2">Clinic, salon ya lab ke liye. Har call uthata hai, booking likhta hai, aur baad mein saabit kar sakta hai ki caller ne kya haan boli.</p>
      <div class="row" data-reveal style="--i:3">
        <a class="btn btn-primary" href="talk">Baat karke dekho <i data-icon="arrow"></i></a>
        <a class="btn btn-ghost" href="#pillars">Kaise kaam karta hai</a>
      </div>
    </div>
    <div class="frame phone" id="hero-call" tabindex="0" aria-label="Ek asli call ka replay — hover ya focus karne pe rukta hai">
      <div class="phone-head"><span class="live"><i></i>LIVE CALL · SMILE CARE DENTAL</span><span class="mono timer">00:00</span></div>
      <div class="transcript" aria-live="polite"></div>
    </div>
  </section>

  <section class="wall section" id="pillars">
    <div class="wrap">
      <span class="eyebrow">Teen cheezein jo kahin aur nahi hain</span>
      <h2>Har ek napi hui hai, likhi nahi.</h2>
      <div class="grid-3 pillars">
        <article class="pillar" data-reveal>
          <span class="badge">Bhasha Bridge</span>
          <p>Aapke apne catalogue se bana sound-index. Recogniser ko bhi batata hai, aur uski galti bhi sudhaarta hai — sirf tab jab wo khud sure na ho aur awaaz bilkul match kare.</p>
          <p class="num"><b>31.6% → 1.1%</b><span>galat sune shabd, 30% noise pe · 0 harmful corrections</span></p>
          <div class="widget" id="w-bhasha"></div>
        </article>
        <article class="pillar" data-reveal style="--i:1">
          <span class="badge">Speculative turns</span>
          <p>Jab caller bol hi raha hota hai, read-only kaam pehle se shuru ho jaata hai. Jawab tab use hota hai jab asli sawaal byte-by-byte wahi nikle.</p>
          <p class="num"><b>239 → 137 ms</b><span>read turns pe median · 45.5% hit rate</span></p>
          <div class="widget bars" id="w-spec">
            <div><span>pehle</span><i style="--w:100%"></i><em>239</em></div>
            <div><span>ab</span><i style="--w:57%"></i><em>137</em></div>
          </div>
        </article>
        <article class="pillar" data-reveal style="--i:2">
          <span class="badge">Pramaan ledger</span>
          <p>Har booking ek signed, chained receipt mein seal hoti hai — caller ki "haan" ke saath. Koi bhi, kahin bhi, bina humpe bharosa kiye verify kar sakta hai.</p>
          <p class="num"><b>80 / 80</b><span>chhedchhad pakdi · 0 bina-confirm writes</span></p>
          <div class="widget chain" id="w-chain" aria-hidden="true"><i></i><i></i><i></i><i class="bad"></i><i class="bad"></i></div>
        </article>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="wrap">
      <span class="eyebrow">Khud try karo</span>
      <h2>Koi key nahi, koi signup nahi.</h2>
      <div class="grid-3" style="margin-top:36px">
        <a class="frame try" href="talk" data-reveal>
          <span class="eyebrow">Live call</span>
          <h3>Talk to HaanJi</h3>
          <p>Mic se bolo ya type karo. Bhasha repair, speculation aur receipt — sab live, engine ke sheeshe mein.</p>
          <span class="go"><i data-icon="arrow"></i></span>
        </a>
        <a class="frame try" href="whatsapp" data-reveal style="--i:1">
          <span class="eyebrow">WhatsApp</span>
          <h3>Same brain, chat pe</h3>
          <p>Wahi agent, text pe. Aur ek missed call button — jo call chhoot gayi usse WhatsApp pe wapas pakadta hai.</p>
          <span class="go"><i data-icon="arrow"></i></span>
        </a>
        <a class="frame try" href="verify" data-reveal style="--i:2">
          <span class="eyebrow">Pramaan</span>
          <h3>Receipt verifier</h3>
          <p>Har hash aur signature aapke browser mein dobara check hota hai. Ek field chhedo aur dekho chain kaise tootti hai.</p>
          <span class="go"><i data-icon="arrow"></i></span>
        </a>
      </div>
    </div>
  </section>

  <section class="wall section">
    <div class="wrap grid-3 open">
      <div data-reveal><h3>Ek file = ek business</h3><p>Dental clinic, salon, lab, coaching — har ek ek YAML pack hai: catalogue, hours, persona, guardrails, aur wo calls jo pack ko ship hone se pehle paas karni hain.</p></div>
      <div data-reveal style="--i:1"><h3>Napa hua, andaaza nahi</h3><p>Upar ka har number <code>python -m haanji.bench</code> se aata hai aur <code>research/results.json</code> mein likha jaata hai. README mein koi estimate nahi hai.</p></div>
      <div data-reveal style="--i:2"><h3>Khud verify karo</h3><p>Receipts ka export lo aur <a href="verify">browser mein</a> har hash aur signature dobara check karo. Humpe bharosa karna zaroori nahi.</p></div>
    </div>
  </section>
</main>

<footer class="wrap foot">
  <span>Open source · <a href="https://github.com/aritra-25hazra/haanji" rel="noopener">GitHub</a></span>
  <span class="mono muted">HaanJi v0.4.0</span>
</footer>

<script src="static/signboard.js"></script>
<script src="static/hero-call.js"></script>
<script>
  Signboard.status().then(function (s) {
    if (s && s.console_url) {
      document.getElementById("console-link").href = s.console_url;
      document.getElementById("console-li").hidden = false;
      Signboard.mountIcons(document.getElementById("console-li"));
    }
  });
  // The Bhasha widget replays three real repairs from the packs.
  (function () {
    const w = document.getElementById("w-bhasha");
    const pairs = [["rut kanal", "root canal", 0.32], ["klining", "cleaning", 0.41], ["sheikh", "Dr Sheikh", 0.55]];
    let i = 0;
    function show() {
      w.innerHTML = "";
      const p = pairs[i % pairs.length];
      const r = Signboard.repairNode({ from_token: p[0], to_surface: p[1], asr_confidence: p[2] });
      w.appendChild(r);
      requestAnimationFrame(function () { Signboard.paintRepair(r); });
      i++;
    }
    show();
    if (!Signboard.REDUCED) setInterval(show, 4000);
  })();
</script>
</body>
</html>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k landing`
Expected: PASS.

- [ ] **Step 6: Look at it**

Run: `cd engine && $PY -m haanji.cli serve --port 8090` in the background, open `http://localhost:8090/` in a browser. Confirm: wordmark paints in, hero call plays through to the stamp, hovering the phone pauses it, pillars reveal on scroll, the bars grow and the chain's fourth block turns sindoor, no horizontal scrollbar at 390 px wide (DevTools device mode). Stop the server.

- [ ] **Step 7: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/web/index.html engine/haanji/web/hero-call.js engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(web): the landing page, with the README's call replayed as the hero

A split hero: the claim on the left, and on the right a phone frame where
the real demo call plays on a loop — the Bhasha repair paints over the
misheard word, the speculated tool shows up ready, and the receipt lands
as a stamp. Below it, the three measured pillars with a small live widget
each, the three ways to try it, and how it is built.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 4: Talk page — call column + engine panel

**Files:**
- Rewrite: `engine/haanji/web/talk.html`
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Consumes: `Signboard.{repairNode, paintRepair, stamp, typingDots, timer, waveform, icon, mountIcons, esc, status, REDUCED}`; API `POST api/sessions {pack, phone}` → `{session_id, greeting, business}`; `POST api/sessions/{sid}/partial {text}`; `POST api/sessions/{sid}/utterance {text}` → `{reply, corrections:[{from_token,to_surface,asr_confidence,key,to_key}], tools, speculation_hits, guard, latency_ms, receipts:[code], end_call, outcome}`; `DELETE api/sessions/{sid}`.
- Produces: ids `log`, `interim`, `panel-bhasha`, `panel-spec`, `panel-pramaan`, `mic`, `text`, `send`, `sheet-toggle`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/test_web.py`:

```python
def test_the_talk_page_has_the_call_and_the_engine_panel(client):
    html = client.get("/talk").text
    for el_id in ("log", "interim", "panel-bhasha", "panel-spec", "panel-pramaan", "mic", "text", "send", "sheet-toggle"):
        assert f'id="{el_id}"' in html, el_id
    assert 'aria-live="polite"' in html
    assert "Start call" in html and "Call khatam karo" in html
    assert "haanji serve" not in html and "localhost" not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k talk_page`
Expected: FAIL.

- [ ] **Step 3: Write `talk.html`**

Replace `engine/haanji/web/talk.html` with:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Talk to HaanJi</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Yatra+One&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/signboard.css">
<style>
  body { height: 100dvh; display: flex; flex-direction: column; overflow: hidden; }
  .topbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; min-height: 72px; padding: 10px 20px; border-bottom: 1px solid rgba(245, 185, 30, .28); }
  .topbar .biz { font-weight: 600; }
  .topbar .timer { font-size: 14px; color: var(--marigold); min-width: 48px; }
  .controls { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; margin-left: auto; }
  .controls .field { min-width: 150px; }
  .notice { margin: 10px 20px 0; padding: 10px 14px; border-radius: var(--r-ctl); background: rgba(226, 85, 58, .18); color: #FFB3A3; font-size: 14px; }
  main.talk { flex: 1; min-height: 0; display: grid; grid-template-columns: 1.15fr 1fr; }
  .call { display: flex; flex-direction: column; min-height: 0; border-right: 1px solid rgba(245, 185, 30, .28); }
  .call .transcript { flex: 1; overflow-y: auto; padding: 22px 20px; }
  .interim { min-height: 22px; padding: 4px 20px; font-size: 14px; font-style: italic; color: var(--haze); }
  .engine { min-height: 0; overflow-y: auto; background: var(--cobalt-deep); padding: 16px; }
  .sheet-toggle { display: none; }
  .engine-cards { display: flex; flex-direction: column; gap: 14px; }
  .ecard { padding: 18px 20px; display: flex; flex-direction: column; gap: 12px; }
  .ecard header { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
  .ecard h2 { font-size: 16px; letter-spacing: .02em; }
  .ecard header a { font-size: 13px; color: var(--marigold); text-decoration: none; display: inline-flex; align-items: center; gap: 4px; }
  .ebody { display: flex; flex-direction: column; gap: 10px; font-size: 14px; }
  .erow { padding: 10px 12px; border-radius: 10px; background: rgba(255, 247, 230, .06); display: flex; flex-direction: column; gap: 6px; }
  .keys { font-size: 12.5px; color: var(--haze); word-break: break-all; }
  .keys .ok { display: inline-flex; align-items: center; gap: 3px; }
  .tl { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--haze); }
  .tl i { width: 10px; height: 10px; border-radius: 50%; background: rgba(255, 247, 230, .2); }
  .tl i.on { background: var(--leaf); }
  .tl i.off { background: var(--haze); opacity: .5; }
  .tl b { font-weight: 500; color: var(--chalk); }
  .bar { display: flex; align-items: center; gap: 12px; padding: 12px 20px 16px; border-top: 1px solid rgba(245, 185, 30, .28); }
  .mic { width: 56px; height: 56px; border-radius: 50%; border: 0; background: var(--marigold); color: var(--cobalt); display: inline-flex; align-items: center; justify-content: center; flex: none; transition: background var(--t-micro), transform var(--t-micro); }
  .mic:active { transform: scale(.95); }
  .mic .ic { width: 24px; height: 24px; }
  .mic.live { background: var(--sindoor); color: var(--chalk); animation: pulse 1.2s infinite; }
  .mic:disabled { opacity: .45; cursor: default; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(226, 85, 58, .5); } 70% { box-shadow: 0 0 0 14px rgba(226, 85, 58, 0); } 100% { box-shadow: 0 0 0 0 rgba(226, 85, 58, 0); } }
  .bar .wave { flex: none; }
  @media (max-width: 900px) {
    main.talk { grid-template-columns: 1fr; }
    .call { border-right: 0; }
    .engine { position: fixed; left: 0; right: 0; bottom: 84px; z-index: 5; max-height: 62dvh; border-top: 1px solid rgba(245, 185, 30, .4); border-radius: 16px 16px 0 0; transform: translateY(calc(100% - 56px)); transition: transform var(--t-base) var(--ease-out); }
    .engine.open { transform: none; }
    .sheet-toggle { display: inline-flex; width: 100%; justify-content: space-between; margin-bottom: 12px; }
    .sheet-toggle .ic { transition: transform var(--t-base); }
    .engine.open .sheet-toggle .ic { transform: rotate(180deg); }
    .controls .field { min-width: 120px; }
  }
</style>
</head>
<body>
<a class="skip" href="#main">Seedha call pe jao</a>
<header class="topbar">
  <a class="wordmark" href="./">HaanJi <span class="dev">हाँजी</span></a>
  <span id="biz" class="biz"></span>
  <span id="timer" class="mono timer">00:00</span>
  <div class="controls">
    <label class="field"><span>Pack</span><select id="pack" class="input"></select></label>
    <label class="field"><span>Phone (optional — try 9876543210)</span><input id="phone" class="input" type="tel" inputmode="numeric" maxlength="10" pattern="\d*" placeholder="9876543210"></label>
    <button class="btn btn-primary" id="start"><i data-icon="phone"></i>Start call</button>
    <button class="btn btn-danger" id="end" hidden><i data-icon="x"></i>Call khatam karo</button>
    <button class="btn btn-ghost" id="mute" aria-pressed="false"><i data-icon="speaker"></i><span>Awaaz on</span></button>
  </div>
</header>
<div id="notice" class="notice" hidden role="status"></div>

<main id="main" class="talk">
  <section class="call" aria-label="Call">
    <div class="transcript" id="log" aria-live="polite">
      <p class="sys" id="empty">Pack chuniye aur "Start call" dabaiye — phir mic se boliye ya neeche type kijiye.<br>Phone 9876543210 daaloge to returning-caller greeting dikhega.</p>
    </div>
    <p class="interim" id="interim"></p>
  </section>

  <aside class="engine" id="engine" aria-label="Engine ka sheesha">
    <button class="btn btn-ghost sheet-toggle" id="sheet-toggle" aria-expanded="false" aria-controls="engine-cards">Engine ka sheesha <i data-icon="chevron"></i></button>
    <div class="engine-cards" id="engine-cards">
      <section class="frame ecard" id="panel-bhasha" aria-live="polite">
        <header><h2>Bhasha Bridge</h2><span class="mono muted" id="bhasha-count">0 repairs</span></header>
        <div class="ebody" id="bhasha-body"><p class="muted">Call shuru hone pe yahan har sudhaar dikhega — kya suna, kya padha, aur kyun.</p></div>
      </section>
      <section class="frame ecard" id="panel-spec" aria-live="polite">
        <header><h2>Speculation</h2><span class="mono muted" id="spec-count">0 / 0 hits</span></header>
        <div class="ebody" id="spec-body"><p class="muted">Tool calls aur unka timing yahan — kaunsa jawab poochne se pehle hi taiyaar tha.</p></div>
      </section>
      <section class="frame ecard" id="panel-pramaan" aria-live="polite">
        <header><h2>Pramaan</h2><a href="verify">Verify karo <i data-icon="arrow" class="ic-sm"></i></a></header>
        <div class="ebody" id="pramaan-body">
          <div class="chain" id="chain" aria-hidden="true"><i class="empty"></i></div>
          <p class="muted" id="pramaan-note">Booking hote hi receipt yahan seal hogi — Ed25519 signed, pichhli se chained.</p>
        </div>
      </section>
    </div>
  </aside>
</main>

<footer class="bar">
  <button class="mic" id="mic" aria-label="Mic — bolne ke liye dabao" aria-pressed="false"><i data-icon="mic"></i></button>
  <div class="wave" id="wave" aria-hidden="true"></div>
  <input class="input input-pill" id="text" placeholder="…ya yahan type karke Enter" aria-label="Message">
  <button class="btn btn-primary btn-icon" id="send" aria-label="Bhejo"><i data-icon="send"></i></button>
</footer>

<script src="static/signboard.js"></script>
<script>
(function () {
  "use strict";
  const S = window.Signboard;
  const $ = function (id) { return document.getElementById(id); };
  let sid = null, muted = false, recog = null, listening = false;
  let repairsTotal = 0, specHits = 0, specStarted = 0;
  const receipts = [];
  const tm = S.timer($("timer"));
  const wave = S.waveform($("wave"));
  let audioCtx = null, stream = null;

  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    if (!r.ok) throw new Error((await r.text()) || String(r.status));
    return r.json();
  }

  function notice(text) { const n = $("notice"); n.textContent = text || ""; n.hidden = !text; }

  S.status().then(function (s) {
    if (!s) { notice("Server se connect nahi ho pa raha — thodi der mein dobara try kijiye."); $("pack").disabled = true; $("start").disabled = true; return; }
    $("pack").innerHTML = s.packs.map(function (p) { return "<option" + (p === s.default_pack ? " selected" : "") + ">" + S.esc(p) + "</option>"; }).join("");
  });

  function row(who, text) {
    $("empty") && $("empty").remove();
    const b = document.createElement("div");
    b.className = "bubble " + who;
    b.textContent = text;
    $("log").appendChild(b);
    $("log").scrollTop = $("log").scrollHeight;
    return b;
  }
  function sys(text) {
    const p = document.createElement("p"); p.className = "sys"; p.textContent = text;
    $("log").appendChild(p); $("log").scrollTop = $("log").scrollHeight;
  }

  function speak(text) {
    if (muted || !window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text);
    const v = speechSynthesis.getVoices().find(function (v) { return /hi[-_]IN/i.test(v.lang); });
    if (v) u.voice = v;
    u.lang = "hi-IN"; u.rate = 1.02;
    speechSynthesis.speak(u);
  }

  function metaFor(t) {
    const meta = document.createElement("div"); meta.className = "meta";
    (t.tools || []).forEach(function (tool) {
      const hit = (t.speculation_hits || []).includes(tool);
      const c = document.createElement("span");
      c.className = "chip " + (hit ? "chip-spec" : "chip-tool");
      c.innerHTML = (hit ? S.icon("bolt") : "") + S.esc(tool) + (hit ? " · speculated" : "");
      meta.appendChild(c);
    });
    if (t.guard) { const g = document.createElement("span"); g.className = "chip chip-guard"; g.innerHTML = S.icon("shield") + "guardrail: " + S.esc(t.guard); meta.appendChild(g); }
    (t.receipts || []).forEach(function (code) {
      const st = document.createElement("span"); st.className = "stamp"; st.innerHTML = S.icon("lock") + "RECEIPT " + S.esc(code); st.style.opacity = "0"; meta.appendChild(st);
    });
    if (t.latency_ms != null) { const m = document.createElement("span"); m.className = "mono muted"; m.textContent = Math.round(t.latency_ms) + " ms"; meta.appendChild(m); }
    return meta;
  }

  function updatePanel(t) {
    // Bhasha
    const bb = $("bhasha-body");
    if (t.corrections && t.corrections.length) {
      repairsTotal += t.corrections.length;
      bb.innerHTML = "";
      t.corrections.forEach(function (c) {
        const rowEl = document.createElement("div"); rowEl.className = "erow";
        const r = S.repairNode(c); rowEl.appendChild(r);
        const k = document.createElement("div"); k.className = "mono keys";
        const exact = c.key && c.key === c.to_key;
        k.innerHTML = S.esc(c.key || "") + " = " + S.esc(c.to_key || "") +
          (exact ? ' <span class="ok">' + S.icon("check", "ic-sm") + "exact</span>" : "") +
          " · conf " + Number(c.asr_confidence).toFixed(2);
        rowEl.appendChild(k);
        bb.appendChild(rowEl);
        requestAnimationFrame(function () { S.paintRepair(r); });
      });
    } else {
      bb.innerHTML = '<p class="muted">Is turn mein kuch sudhaarna nahi pada.</p>';
    }
    $("bhasha-count").textContent = repairsTotal + (repairsTotal === 1 ? " repair" : " repairs");

    // Speculation
    const sb = $("spec-body");
    if (t.tools && t.tools.length) {
      sb.innerHTML = "";
      t.tools.forEach(function (tool) {
        const hit = (t.speculation_hits || []).includes(tool);
        specStarted += 1; if (hit) specHits += 1;
        const rowEl = document.createElement("div"); rowEl.className = "erow";
        rowEl.innerHTML =
          '<div class="row"><b class="mono">' + S.esc(tool) + "</b>" +
          '<span class="chip ' + (hit ? "chip-spec" : "chip-tool") + '">' + (hit ? S.icon("bolt") + "hit" : "miss") + "</span></div>" +
          (hit
            ? '<div class="tl"><i class="on"></i><b>shuru</b><i class="on"></i><b>tayyar</b><i class="on"></i><b>poocha</b><span>— jawab pehle se tha</span></div>'
            : '<div class="tl"><i class="on"></i><b>shuru</b><i class="on"></i><b>poocha</b><i class="off"></i><b>tayyar</b><span>— poochne ke baad bana</span></div>') +
          '<div class="mono muted">' + Math.round(t.latency_ms || 0) + " ms</div>";
        sb.appendChild(rowEl);
      });
    }
    $("spec-count").textContent = specHits + " / " + specStarted + " hits";

    // Pramaan
    if (t.receipts && t.receipts.length) {
      t.receipts.forEach(function (code) { receipts.push(code); });
      const chain = $("chain"); chain.innerHTML = "";
      receipts.forEach(function () { chain.appendChild(document.createElement("i")); });
      const empty = document.createElement("i"); empty.className = "empty"; chain.appendChild(empty);
      const note = $("pramaan-note");
      note.innerHTML = "";
      const st = document.createElement("span"); st.className = "stamp"; st.innerHTML = S.icon("lock") + "RECEIPT " + S.esc(receipts[receipts.length - 1]);
      st.style.opacity = "0"; note.appendChild(st);
      const line = document.createElement("div"); line.className = "mono muted"; line.style.marginTop = "8px";
      line.textContent = "seq " + receipts.length + " · sealed · Ed25519 · chained to seq " + (receipts.length - 1);
      note.appendChild(line);
      requestAnimationFrame(function () { S.stamp(st); });
    }
  }

  function resetPanel() {
    repairsTotal = 0; specHits = 0; specStarted = 0; receipts.length = 0;
    $("bhasha-body").innerHTML = '<p class="muted">Call shuru — pehla turn aane do.</p>';
    $("bhasha-count").textContent = "0 repairs";
    $("spec-body").innerHTML = '<p class="muted">Tool calls aur unka timing yahan.</p>';
    $("spec-count").textContent = "0 / 0 hits";
    $("chain").innerHTML = '<i class="empty"></i>';
    $("pramaan-note").innerHTML = '<p class="muted">Booking hote hi receipt yahan seal hogi — Ed25519 signed, pichhli se chained.</p>';
  }

  async function startCall() {
    const phone = $("phone").value.trim();
    const res = await api("api/sessions", { method: "POST", body: JSON.stringify({ pack: $("pack").value, phone: phone || null }) });
    sid = res.session_id;
    $("log").innerHTML = "";
    resetPanel();
    document.title = res.business + " — HaanJi";
    $("biz").textContent = res.business;
    row("agent", res.greeting); speak(res.greeting);
    $("start").hidden = true; $("end").hidden = false;
    tm.start();
    $("text").focus();
  }

  async function endCall(silent) {
    if (sid) await api("api/sessions/" + sid, { method: "DELETE" }).catch(function () {});
    sid = null;
    $("start").hidden = false; $("end").hidden = true;
    tm.stop();
    if (!silent) sys("Call khatam");
    stopMic();
  }

  async function sendUtterance(text) {
    if (!text.trim()) return;
    if (!sid) await startCall();
    if (window.speechSynthesis) speechSynthesis.cancel();          // barge-in
    const callerBubble = row("caller", text);
    const typing = S.typingDots(); $("log").appendChild(typing); $("log").scrollTop = $("log").scrollHeight;
    let t;
    try { t = await api("api/sessions/" + sid + "/utterance", { method: "POST", body: JSON.stringify({ text: text }) }); }
    catch (e) { typing.remove(); sys("Jawab nahi aaya — dobara try kijiye."); return; }
    typing.remove();
    if (t.corrections && t.corrections.length) {
      const meta = document.createElement("div"); meta.className = "meta";
      t.corrections.forEach(function (c) { meta.appendChild(S.repairNode(c)); });
      callerBubble.appendChild(meta);
      meta.querySelectorAll(".repair").forEach(function (r) { S.paintRepair(r); });
    }
    const agent = row("agent", t.reply);
    const meta = metaFor(t);
    if (meta.children.length) agent.appendChild(meta);
    meta.querySelectorAll(".stamp").forEach(function (st) { S.stamp(st); });
    updatePanel(t);
    speak(t.reply);
    if (t.end_call) {
      sid = null; $("start").hidden = false; $("end").hidden = true; tm.stop(); stopMic();
      sys("Call khatam — outcome " + (t.outcome || "").replace(/_/g, " ").toLowerCase());
    }
  }

  function sendPartial(text) {
    if (sid && text.trim()) {
      fetch("api/sessions/" + sid + "/partial", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text }) });
    }
  }

  // ── microphone: Web Speech API; the text box is the universal fallback.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) {
    recog = new SR();
    recog.lang = "hi-IN"; recog.interimResults = true; recog.continuous = false;
    let finalText = "";
    recog.onresult = function (e) {
      let interim = ""; finalText = "";
      for (const r of e.results) { if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript; }
      $("interim").textContent = interim || finalText;
      if (interim) sendPartial(interim);
    };
    recog.onend = function () {
      listening = false; setMic(false);
      const text = finalText.trim(); finalText = ""; $("interim").textContent = "";
      if (text) sendUtterance(text);
    };
    recog.onerror = function () { listening = false; setMic(false); $("interim").textContent = "Mic error — type kijiye, ya Chrome try kijiye."; };
  } else {
    $("mic").disabled = true;
    $("mic").title = "Is browser mein mic nahi — type kijiye (Chrome best)";
  }

  function setMic(on) {
    $("mic").classList.toggle("live", on);
    $("mic").setAttribute("aria-pressed", String(on));
    $("mic").innerHTML = S.icon(on ? "micOff" : "mic");
    wave.setLive(on);
  }
  async function attachAnalyser() {
    if (audioCtx || !navigator.mediaDevices) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const an = audioCtx.createAnalyser(); an.fftSize = 512;
      audioCtx.createMediaStreamSource(stream).connect(an);
      wave.attach(an);
    } catch (e) { /* no analyser: the idle pattern is used instead */ }
  }
  function stopMic() {
    if (listening && recog) { try { recog.stop(); } catch (e) {} }
    listening = false; setMic(false);
    wave.detach();
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    if (audioCtx) { audioCtx.close().catch(function () {}); audioCtx = null; }
  }

  $("mic").onclick = async function () {
    if (!recog) return;
    if (!sid) await startCall();
    if (listening) { recog.stop(); return; }
    if (window.speechSynthesis) speechSynthesis.cancel();          // barge-in on the agent
    listening = true; setMic(true);
    attachAnalyser();
    recog.start();
  };
  $("start").onclick = startCall;
  $("end").onclick = function () { endCall(false); };
  $("mute").onclick = function () {
    muted = !muted;
    $("mute").setAttribute("aria-pressed", String(muted));
    $("mute").innerHTML = S.icon(muted ? "speakerOff" : "speaker") + "<span>" + (muted ? "Awaaz off" : "Awaaz on") + "</span>";
    if (muted && window.speechSynthesis) speechSynthesis.cancel();
  };
  $("send").onclick = function () { sendUtterance($("text").value); $("text").value = ""; };
  $("text").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { sendUtterance($("text").value); $("text").value = ""; }
    else if (sid && $("text").value.length % 6 === 5) sendPartial($("text").value);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && sid) endCall(false); });
  $("sheet-toggle").onclick = function () {
    const open = $("engine").classList.toggle("open");
    $("sheet-toggle").setAttribute("aria-expanded", String(open));
  };
  window.addEventListener("beforeunload", function () {
    if (sid) fetch("api/sessions/" + sid, { method: "DELETE", keepalive: true });
  });
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k talk_page`
Expected: PASS.

- [ ] **Step 5: Try a call**

Start the server, open `http://localhost:8090/talk`, click **Start call**, type `haan ji mujhe rut kanal karwana tha`, Enter. Confirm: the caller bubble gets a painted repair, the Bhasha card shows the two equal sound keys with the check icon, the agent bubble shows its ms. Type `kal subah ka time mil jayega`: the Speculation card shows `check_availability` with a hit or miss timeline. Type `haan confirm kar do`, then `Vijay Sharma 9876543210` if asked for name and number: a stamp lands on the agent bubble and on the Pramaan card, the chain grows by one block. Narrow the window below 900 px: the panel becomes a bottom sheet with a working toggle. Press Escape: the call ends. Stop the server.

- [ ] **Step 6: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/web/talk.html engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(web): the call page, with the engine's three pieces live beside it

The transcript keeps every behaviour it had — Web Speech, partial
transcripts for speculation, barge-in, voice replies — and gains the
Signboard look: painted repairs under what was heard, stamps where a
receipt was sealed, a timer and a waveform that follows the mic.

Beside it, an engine panel that was not there before: Bhasha shows the
sound-key match that justified each repair, Speculation shows each tool
call and whether its answer was ready before it was asked for, and Pramaan
shows the chain growing one block per receipt. On narrow screens the panel
is a bottom sheet.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 5: WhatsApp page

**Files:**
- Rewrite: `engine/haanji/web/whatsapp.html`
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Consumes: `Signboard.{repairNode, paintRepair, stamp, icon, mountIcons, esc, status}`; API `GET api/wa/threads?pack=` → `{threads:[{phone, messages, last_at}]}`; `GET api/wa/threads/{phone}?pack=` → `{messages:[{direction:"in"|"out", text, at, meta_json}]}`; `POST api/wa/incoming {pack, phone, text}`; `POST api/telephony/missed-call {pack, phone}`.
- Produces: ids `threads`, `msgs`, `missed`, `open`, `phone`, `text`, `send`, `pack`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/test_web.py`:

```python
def test_the_whatsapp_page_keeps_its_simulator_controls(client):
    html = client.get("/whatsapp").text
    for el_id in ("threads", "msgs", "missed", "open", "phone", "text", "send", "pack"):
        assert f'id="{el_id}"' in html, el_id
    assert "missed call" in html.lower()
    assert 'href="static/signboard.css"' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k whatsapp`
Expected: FAIL (no `signboard.css` link in the old page).

- [ ] **Step 3: Write `whatsapp.html`**

Replace `engine/haanji/web/whatsapp.html` with:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HaanJi — WhatsApp simulator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Yatra+One&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/signboard.css">
<style>
  /* The chat canvas stays WhatsApp-like on purpose: same brain, different channel. */
  :root { --wa-bg: #0B141A; --wa-panel: #111B21; --wa-line: #233138; --wa-head: #202C33; --wa-in: #202C33; --wa-out: #005C4B; --wa-accent: #00A884; --wa-mist: #8696A0; }
  body { height: 100dvh; display: flex; overflow: hidden; }
  aside { width: 340px; min-width: 280px; display: flex; flex-direction: column; background: var(--cobalt-deep); border-right: 1px solid rgba(245, 185, 30, .28); }
  aside .head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; border-bottom: 1px solid rgba(245, 185, 30, .28); }
  aside .head a.back { color: var(--haze); font-size: 13px; text-decoration: none; }
  .newthread { display: flex; gap: 8px; padding: 12px 14px; border-bottom: 1px solid rgba(245, 185, 30, .18); }
  .newthread .input { flex: 1; min-width: 0; }
  .missed { padding: 12px 14px; border-bottom: 1px solid rgba(245, 185, 30, .18); display: flex; flex-direction: column; gap: 8px; }
  .missed .btn { width: 100%; }
  .missed p { color: var(--haze); font-size: 13px; }
  #threads { flex: 1; overflow-y: auto; }
  .thread { width: 100%; text-align: left; background: none; border: 0; border-bottom: 1px solid rgba(255, 247, 230, .08); padding: 13px 16px; display: flex; flex-direction: column; gap: 2px; min-height: 56px; }
  .thread:hover, .thread.active { background: rgba(255, 247, 230, .07); }
  .thread b { font-size: 15px; }
  .thread span { color: var(--haze); font-size: 12px; }
  main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--wa-bg); color: #E9EDEF; }
  .chathead { display: flex; align-items: center; gap: 12px; padding: 10px 18px; background: var(--cobalt); border-bottom: 1px solid rgba(245, 185, 30, .28); min-height: 64px; }
  .avatar { width: 38px; height: 38px; border-radius: 50%; background: var(--marigold); color: var(--cobalt); display: flex; align-items: center; justify-content: center; font-weight: 800; font-family: var(--font-display); flex: none; }
  .chathead small { display: block; color: var(--haze); font-size: 12px; }
  .chathead select { margin-left: auto; }
  #msgs { flex: 1; overflow-y: auto; padding: 20px 8%; background-image: radial-gradient(rgba(255, 255, 255, .03) 1px, transparent 1px); background-size: 22px 22px; }
  .m { display: flex; margin: 6px 0; }
  .m.out { justify-content: flex-end; }
  .b { max-width: 72%; padding: 8px 12px; border-radius: 10px; font-size: 15px; white-space: pre-wrap; }
  .m.in .b { background: var(--wa-in); border-top-left-radius: 2px; }
  .m.out .b { background: var(--wa-out); border-top-right-radius: 2px; }
  .time { font-size: 11px; color: var(--wa-mist); margin-top: 4px; text-align: right; font-family: var(--font-mono); }
  .b .meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
  .b .repair { font-size: 14px; }
  .b .repair s { color: var(--wa-mist); }
  .b .repair b { color: var(--marigold); }
  .b .stamp { font-size: 12px; padding: 4px 9px; }
  .compose { display: flex; gap: 10px; padding: 12px 16px; background: var(--wa-head); }
  .compose .input { background: var(--wa-panel); border-color: var(--wa-line); color: #E9EDEF; }
  .compose .btn-icon { border-radius: 50%; background: var(--wa-accent); color: #06110D; }
  .empty { margin: auto; text-align: center; color: var(--wa-mist); max-width: 440px; display: flex; flex-direction: column; gap: 10px; }
  .empty h2 { font-size: 24px; color: #E9EDEF; }
  .sysline { display: flex; justify-content: center; margin: 12px 0; }
  @media (max-width: 760px) {
    body { flex-direction: column; }
    aside { width: 100%; min-width: 0; max-height: 44dvh; border-right: 0; border-bottom: 1px solid rgba(245, 185, 30, .28); }
    #msgs { padding: 16px 12px; }
    .b { max-width: 86%; }
  }
</style>
</head>
<body>
<a class="skip" href="#msgs">Seedha chat pe jao</a>
<aside aria-label="Threads">
  <div class="head">
    <a class="wordmark" href="./">HaanJi <span class="dev">हाँजी</span></a>
    <a class="back" href="./">WhatsApp simulator</a>
  </div>
  <div class="newthread">
    <input id="phone" class="input" type="tel" inputmode="numeric" maxlength="10" placeholder="10-digit number, e.g. 9812345678" aria-label="Phone number">
    <button id="open" class="btn btn-primary">Kholo</button>
  </div>
  <div class="missed">
    <button id="missed" class="btn btn-primary"><i data-icon="phoneMissed"></i>Simulate a missed call</button>
    <p>Telephony webhook fire hota hai → HaanJi khud WhatsApp pe pehla message bhejta hai → reply se booking hui to missed call "recovered" ginti hai.</p>
  </div>
  <div id="threads" role="list"></div>
</aside>
<main>
  <div class="chathead">
    <div class="avatar" id="av" aria-hidden="true">H</div>
    <div><b id="who">Koi thread chuniye</b><small id="biz"></small></div>
    <label class="field" style="margin-left:auto"><span>Pack</span><select id="pack" class="input"></select></label>
  </div>
  <div id="msgs" tabindex="-1">
    <div class="empty">
      <h2>WhatsApp channel demo</h2>
      <p>Left mein number daal ke thread kholo — ya "Simulate a missed call" dabao aur dekho HaanJi khud pehla message bhejta hai. Same engine, same policy, same ledger — sirf channel alag.</p>
    </div>
  </div>
  <div class="compose">
    <input id="text" class="input input-pill" placeholder="Message" disabled aria-label="Message">
    <button id="send" class="btn btn-icon" disabled aria-label="Bhejo"><i data-icon="send"></i></button>
  </div>
</main>

<script src="static/signboard.js"></script>
<script>
(function () {
  "use strict";
  const S = window.Signboard;
  const $ = function (id) { return document.getElementById(id); };
  let phone = null;

  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  S.status().then(function (s) {
    if (!s) return;
    $("pack").innerHTML = s.packs.map(function (p) { return "<option" + (p === s.default_pack ? " selected" : "") + ">" + S.esc(p) + "</option>"; }).join("");
    loadThreads();
  });

  async function loadThreads() {
    const t = await api("api/wa/threads?pack=" + encodeURIComponent($("pack").value));
    $("threads").innerHTML = t.threads.map(function (x) {
      return '<button class="thread' + (x.phone === phone ? " active" : "") + '" data-p="' + S.esc(x.phone) + '" role="listitem">' +
        "<b>+91 " + S.esc(x.phone) + "</b><span>" + x.messages + " messages · " + S.esc(x.last_at.slice(11, 16)) + "</span></button>";
    }).join("");
    document.querySelectorAll(".thread").forEach(function (el) { el.onclick = function () { openThread(el.dataset.p); }; });
  }

  function renderMsg(m) {
    const meta = JSON.parse(m.meta_json || "{}");
    const wrap = document.createElement("div");
    if (meta.missed_call_recovery) {
      const sysEl = document.createElement("div"); sysEl.className = "sysline";
      sysEl.innerHTML = '<span class="chip">' + S.icon("phoneMissed") + "missed call → HaanJi ne khud message bheja</span>";
      wrap.appendChild(sysEl);
    }
    // The caller's own messages (direction "in" to the business) sit on the right, as a phone would show them.
    const row = document.createElement("div"); row.className = "m " + (m.direction === "in" ? "out" : "in");
    const b = document.createElement("div"); b.className = "b"; b.textContent = m.text;
    const metaEl = document.createElement("div"); metaEl.className = "meta";
    (meta.corrections || []).forEach(function (c) { metaEl.appendChild(S.repairNode(c)); });
    (meta.tools || []).forEach(function (t) { const c = document.createElement("span"); c.className = "chip chip-tool"; c.textContent = t; metaEl.appendChild(c); });
    (meta.receipts || []).forEach(function (r) { const st = document.createElement("span"); st.className = "stamp"; st.innerHTML = S.icon("lock") + "RECEIPT " + S.esc(r); metaEl.appendChild(st); });
    if (metaEl.children.length) b.appendChild(metaEl);
    const time = document.createElement("div"); time.className = "time"; time.textContent = m.at.slice(11, 16);
    b.appendChild(time); row.appendChild(b); wrap.appendChild(row);
    return wrap;
  }

  async function openThread(p) {
    phone = p; $("phone").value = p;
    $("who").textContent = "+91 " + p;
    $("av").textContent = p.slice(-2);
    $("biz").textContent = "HaanJi · " + $("pack").value;
    $("text").disabled = $("send").disabled = false;
    const t = await api("api/wa/threads/" + encodeURIComponent(p) + "?pack=" + encodeURIComponent($("pack").value));
    const box = $("msgs"); box.innerHTML = "";
    t.messages.forEach(function (m) { box.appendChild(renderMsg(m)); });
    box.querySelectorAll(".repair").forEach(function (r) { S.paintRepair(r); });
    box.scrollTop = box.scrollHeight;
    loadThreads();
    $("text").focus();
  }

  async function send() {
    const text = $("text").value.trim();
    if (!text || !phone) return;
    $("text").value = "";
    await api("api/wa/incoming", { method: "POST", body: JSON.stringify({ pack: $("pack").value, phone: phone, text: text }) });
    await openThread(phone);
    const last = $("msgs").querySelector(".m:last-of-type .stamp");
    if (last) S.stamp(last);
  }

  $("open").onclick = function () {
    const p = $("phone").value.trim();
    if (/^\d{10}$/.test(p)) openThread(p);
    else { $("phone").setCustomValidity("10 digit ka number chahiye"); $("phone").reportValidity(); setTimeout(function () { $("phone").setCustomValidity(""); }, 1500); }
  };
  $("missed").onclick = async function () {
    const p = $("phone").value.trim() || String(9700000000 + Math.floor(Math.random() * 9999999));
    $("phone").value = p;
    await api("api/telephony/missed-call", { method: "POST", body: JSON.stringify({ pack: $("pack").value, phone: p }) });
    openThread(p);
  };
  $("send").onclick = send;
  $("text").addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  $("pack").onchange = loadThreads;
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k whatsapp`
Expected: PASS.

- [ ] **Step 5: Try it**

Start the server, open `http://localhost:8090/whatsapp`, click **Simulate a missed call**: a thread opens with the missed-call chip and HaanJi's first message. Reply `haan root canal chahiye kal subah`, then follow through to a booking: a stamp appears in the last bubble. Narrow below 760 px: the thread list stacks on top. Stop the server.

- [ ] **Step 6: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/web/whatsapp.html engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(web): the WhatsApp simulator in Signboard chrome

The chat canvas keeps its WhatsApp look — that is the point of the page —
while the thread list, header and controls join the rest of the demo. The
painted repair and stamp read inside the green bubbles, the missed-call
recovery is a chip with its own icon, and the thread rows are real buttons.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 6: Verify page

**Files:**
- Rewrite: `engine/haanji/web/verify.html`
- Test: `engine/tests/test_web.py` (append)

**Interfaces:**
- Consumes: `Signboard.{stamp, icon, mountIcons, esc, status}`; `static/nacl-fast.min.js` (global `nacl`) and `static/verifier.js` (global `PramaanVerifier.verifyChain(exp, nacl)` → `{ok, checked, firstBrokenSeq, reason, rows:[{seq, action, code, ok: true|false|null, reason}]}`), both unchanged; API `GET api/receipts/export?pack=` → `{tenant_id, public_key, receipts:[...]}`.
- Produces: ids `verdict`, `chainstrip`, `rows`, `tbl`, `load`, `paste`, `tamper`, `json`, `key`, `pack`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/test_web.py`:

```python
def test_the_verify_page_has_its_verdict_chain_and_register(client):
    html = client.get("/verify").text
    for el_id in ("verdict", "chainstrip", "rows", "tbl", "load", "paste", "tamper", "json", "key", "pack"):
        assert f'id="{el_id}"' in html, el_id
    assert 'src="static/nacl-fast.min.js"' in html and 'src="static/verifier.js"' in html
    assert 'href="static/signboard.css"' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k verify_page`
Expected: FAIL.

- [ ] **Step 3: Write `verify.html`**

Replace `engine/haanji/web/verify.html` with:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pramaan — public receipt verifier</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Yatra+One&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/signboard.css">
<style>
  main { padding: 24px 0 80px; }
  h1 { font-size: clamp(36px, 5vw, 56px); margin: 16px 0 8px; }
  .sub { max-width: 68ch; color: var(--haze); margin-bottom: 24px; }
  .sub b { color: var(--chalk); }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 14px; }
  .tamper-note { font-size: 13px; color: #FFB3A3; }
  textarea.input { width: 100%; height: 140px; padding: 12px; font: 13px/1.5 var(--font-mono); resize: vertical; }
  .verdict { display: none; margin: 22px 0 10px; }
  .verdict.show { display: inline-flex; }
  .verdict.stamp { font-size: 18px; padding: 12px 18px; gap: 12px; flex-wrap: wrap; }
  .verdict small { font-family: var(--font-body); font-weight: 400; font-size: 13px; letter-spacing: 0; opacity: .85; }
  .keyline { font: 12px/1.6 var(--font-mono); color: var(--haze); word-break: break-all; margin: 10px 0 16px; }
  .chainstrip { margin: 8px 0 20px; }
  .chainstrip i { width: 40px; height: 16px; }
  .register { width: 100%; border-collapse: collapse; font-size: 14px; }
  .register th { text-align: left; color: var(--haze); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; padding: 10px 10px; border-bottom: 2px solid rgba(245, 185, 30, .5); }
  .register td { padding: 11px 10px; border-bottom: 1px solid rgba(255, 247, 230, .14); vertical-align: top; }
  .register td.mono { font-size: 13px; }
  .st-ok { color: var(--leaf); font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
  .st-bad { color: #FFB3A3; font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
  .st-skip { color: var(--haze); }
  .how { margin-top: 36px; padding: 20px 22px; border-radius: var(--r-card); background: var(--chalk); color: var(--ink); font-size: 15px; }
  .how b { color: var(--cobalt); }
  .how i { font-style: italic; font-family: var(--font-mono); font-size: 13px; }
</style>
</head>
<body>
<a class="skip" href="#main">Seedha verifier pe jao</a>
<header class="wrap">
  <nav class="nav" aria-label="Main">
    <a class="wordmark" href="./">HaanJi <span class="dev">हाँजी</span></a>
    <ul><li><a href="talk">Demo</a></li><li><a href="whatsapp">WhatsApp</a></li><li><a href="https://github.com/aritra-25hazra/haanji" rel="noopener"><i data-icon="github" class="ic-sm"></i>GitHub</a></li></ul>
  </nav>
</header>
<main id="main" class="wrap">
  <span class="eyebrow">Pramaan ledger</span>
  <h1>Public <span class="dev">सबूत</span> verifier</h1>
  <p class="sub">Har hash aur har Ed25519 signature <b>aapke browser mein</b> dobara compute hota hai — server pe bharosa kiye bina. Export load kijiye, verify kijiye, phir kisi field se chhedchhad karke dekhiye ki chain kaise tootti hai.</p>

  <div class="controls">
    <label class="field"><span>Pack</span><select id="pack" class="input"></select></label>
    <button class="btn btn-primary" id="load">Is server ka export load karo</button>
    <button class="btn btn-ghost" id="paste">Pasted JSON verify karo</button>
    <button class="btn btn-danger" id="tamper" disabled><i data-icon="x"></i>Ek field chhedo aur dobara check karo</button>
    <span class="tamper-note">sirf aapke browser mein — server pe kuch nahi badalta</span>
  </div>
  <textarea id="json" class="input" aria-label="Export JSON" placeholder='…ya kisi bhi HaanJi export ka JSON yahan paste kijiye ({"tenant_id": …, "public_key": …, "receipts": […]})'></textarea>

  <div id="verdict" class="stamp verdict" role="status" aria-live="polite"></div>
  <div class="keyline" id="key"></div>
  <div class="chain chainstrip" id="chainstrip" aria-hidden="true"></div>

  <div style="overflow-x:auto">
    <table id="tbl" class="register" hidden>
      <thead><tr><th>Seq</th><th>Action</th><th>Code</th><th>Verdict</th><th>Reason</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>

  <div class="how">
    <b>Ye page kya karta hai:</b> har receipt ka payload hash uske stored fields se dobara banata hai (canonical JSON — sorted keys, no whitespace), chain link (<i>prev_hash‖payload_hash</i>) recompute karta hai, aur signature ko tenant ki public key se check karta hai (Ed25519, TweetNaCl). Ek bhi character badla → us receipt ka hash badla → aage ki poori chain toot gayi. Kuch bhi is server pe wapas nahi jaata.
  </div>
</main>

<script src="static/nacl-fast.min.js"></script>
<script src="static/verifier.js"></script>
<script src="static/signboard.js"></script>
<script>
(function () {
  "use strict";
  const S = window.Signboard;
  const $ = function (id) { return document.getElementById(id); };
  let current = null;

  S.status().then(function (s) {
    if (!s) return;
    $("pack").innerHTML = s.packs.map(function (p) { return "<option" + (p === s.default_pack ? " selected" : "") + ">" + S.esc(p) + "</option>"; }).join("");
  });

  function chainStrip(rows, firstBroken) {
    const strip = $("chainstrip"); strip.innerHTML = "";
    rows.forEach(function (r) {
      const i = document.createElement("i");
      if (firstBroken != null && r.seq >= firstBroken) i.className = "bad";
      strip.appendChild(i);
    });
  }

  async function run(exp, label) {
    current = exp;
    $("tamper").disabled = false;
    $("key").textContent = "tenant " + exp.tenant_id + " · public key (Ed25519): " + (exp.public_key || "—");
    const rep = await PramaanVerifier.verifyChain(exp, nacl);
    const v = $("verdict");
    v.className = "stamp verdict show" + (rep.ok ? " leaf" : "");
    v.innerHTML = rep.ok
      ? S.icon("check") + "VALID · " + rep.checked + " receipts · chain intact" + (label ? "<small>" + S.esc(label) + "</small>" : "")
      : S.icon("x") + "BROKEN at seq " + rep.firstBrokenSeq + " · " + S.esc(rep.reason || "") + (label ? "<small>" + S.esc(label) + "</small>" : "");
    S.stamp(v);
    chainStrip(rep.rows, rep.ok ? null : rep.firstBrokenSeq);
    $("tbl").hidden = false;
    $("rows").innerHTML = rep.rows.map(function (r) {
      const verdict = r.ok === true ? '<span class="st-ok">' + S.icon("check", "ic-sm") + "verified</span>"
        : r.ok === false ? '<span class="st-bad">' + S.icon("x", "ic-sm") + "BROKEN</span>"
        : '<span class="st-skip">skipped</span>';
      return "<tr><td class=\"mono\">" + r.seq + "</td><td>" + S.esc(r.action) + "</td>" +
        '<td class="mono">' + S.esc(r.code.slice(0, 4)) + "-" + S.esc(r.code.slice(4, 8)) + "</td>" +
        "<td>" + verdict + "</td><td>" + S.esc(r.reason || "hash + link + signature, teeno dobara bane") + "</td></tr>";
    }).join("");
    if (!rep.rows.length) {
      $("rows").innerHTML = '<tr><td colspan="5" class="muted">Export mein koi receipt nahi — pehle <a href="talk">Talk</a> ya <a href="whatsapp">WhatsApp</a> pe ek booking kijiye.</td></tr>';
    }
  }

  $("load").onclick = async function () {
    const r = await fetch("api/receipts/export?pack=" + encodeURIComponent($("pack").value));
    const exp = await r.json();
    $("json").value = JSON.stringify(exp, null, 1).slice(0, 4000);
    run(exp, "loaded live from this server");
  };
  $("paste").onclick = function () {
    try { run(JSON.parse($("json").value), "pasted export"); }
    catch (e) { $("json").setCustomValidity("JSON parse nahi hua: " + e.message); $("json").reportValidity(); setTimeout(function () { $("json").setCustomValidity(""); }, 2500); }
  };
  $("tamper").onclick = function () {
    if (!current || !current.receipts.length) return;
    const t = JSON.parse(JSON.stringify(current));
    const victim = t.receipts[Math.floor(t.receipts.length / 2)];
    try {
      const args = JSON.parse(victim.action_args);
      if (args.time) args.time = "18:00";
      else if (args.service) args.service = "dental implant";
      else args.__edited = true;
      victim.action_args = JSON.stringify(args);
    } catch (e) { victim.transcript_excerpt = "caller: haan"; }
    run(t, "after editing receipt seq " + victim.seq + " locally");
  };
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k verify_page`
Expected: PASS.

- [ ] **Step 5: Try it**

Start the server, make one booking on `/talk`, open `/verify`, click **Is server ka export load karo**: a leaf VALID stamp lands, the chain strip shows one marigold block, the register has one verified row. Click **Ek field chhedo…**: the stamp turns sindoor BROKEN, the block turns sindoor. Stop the server.

- [ ] **Step 6: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/haanji/web/verify.html engine/tests/test_web.py
$G commit -q -F - <<'MSG'
feat(web): the verifier, with the verdict as a stamp and the chain drawn

Same in-browser verification as before — nothing leaves the page — with the
verdict landing as a stamp (leaf when intact, sindoor at the first broken
seq), a strip of chain blocks that breaks visibly where the chain does, and
the receipts laid out like a register.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 7: The two global rules as tests — no emoji, relative URLs

**Files:**
- Test: `engine/tests/test_web.py` (append)
- Possibly modify: any of the four pages or two scripts, if a test catches a slip.

- [ ] **Step 1: Write the tests**

Append to `engine/tests/test_web.py`:

```python
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
ROOT_RELATIVE = re.compile(r'(?:href|src|action)="/[^/]|fetch\("/|open\("[A-Z]+",\s*"/')


def _web_files():
    for name in sorted(os.listdir(WEB)):
        if name.endswith((".html", ".js")) and name not in ("nacl-fast.min.js", "verifier.js"):
            with open(os.path.join(WEB, name), encoding="utf-8") as f:
                yield name, f.read()


@pytest.mark.parametrize("name,text", list(_web_files()))
def test_no_emoji_is_used_as_an_icon(name, text):
    found = EMOJI.findall(text)
    assert not found, f"{name}: {found[:5]} — use Signboard.icon() instead"


@pytest.mark.parametrize("name,text", list(_web_files()))
def test_every_url_is_relative_so_the_page_works_behind_a_prefix(name, text):
    hits = ROOT_RELATIVE.findall(text)
    assert not hits, f"{name}: {hits[:5]} — drop the leading slash"
```

- [ ] **Step 2: Run them**

Run: `cd engine && $PY -m pytest tests/test_web.py -v -k "emoji or relative"`
Expected: all pass. If one fails, the message names the file and the offending text; fix the page (replace the emoji with `<i data-icon="…"></i>` / `S.icon(…)`, or drop the leading slash) and re-run.

- [ ] **Step 3: Run the whole suite**

Run: `cd engine && $PY -m pytest -q`
Expected: `182 passed, 0 failed` — 161 original + 21 in `test_web.py` (3 server + 2 design system + 4 pages + 2 rules × 6 files).

- [ ] **Step 4: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/tests/test_web.py engine/haanji/web/
$G commit -q -F - <<'MSG'
test(web): the two rules the pages must keep

No emoji as icons, and no root-relative URL — the second is what lets the
same files serve at /talk on the engine and at /engine/talk through the
console's rewrite. Both are now checked on every page and script.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 8: Console links, nginx proxy, Render env, keep-awake

**Files:**
- Modify: `console/src/App.tsx:33,36`
- Modify: `console/src/pages/PackStudio.tsx:142`
- Modify: `console/nginx.conf:9-13`
- Modify: `render.yaml` (envVars)
- Create: `.github/workflows/keep-awake.yml`

- [ ] **Step 1: Point the console at the engine through its proxy**

In `console/src/App.tsx` replace the two anchors:

```tsx
          <a href="/engine/talk" target="_blank" rel="noopener noreferrer">
            Talk to HaanJi ↗
          </a>
          <a href="/engine/whatsapp" target="_blank" rel="noopener noreferrer">
            WhatsApp demo ↗
          </a>
```

In `console/src/pages/PackStudio.tsx` replace the anchor:

```tsx
              <a className="btn" href="/engine/talk" target="_blank" rel="noopener">
                Try it live ↗
              </a>
```

In `console/nginx.conf`, after the `/api/` block add:

```nginx
    # The engine's demo pages and JSON, with the prefix stripped — the same
    # shape vite.config.ts proxies in development and vercel.json in production.
    location /engine/ {
        proxy_pass http://engine:8090/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
```

- [ ] **Step 2: Verify the console still builds and has no localhost left**

Run: `cd console && npm run build 2>&1 | tail -3 && grep -rn "localhost:8090" src/ ; echo "exit=$?"`
Expected: `✓ built in …` and the grep prints nothing (exit=1 from grep is fine).

- [ ] **Step 3: Tell Render where the console lives**

In `render.yaml`, append to `envVars`:

```yaml
      # Where the owner console is hosted, so the landing page can link to it.
      - key: HAANJI_CONSOLE_URL
        value: https://haanji-kappa.vercel.app
```

- [ ] **Step 4: Keep the free instance awake**

Create `.github/workflows/keep-awake.yml`:

```yaml
# Render's free plan spins the engine down after 15 idle minutes and the next
# visitor waits ~25 s for it to come back. A request every 10 minutes keeps
# it warm; one always-on service fits inside the plan's monthly free hours.
# Delete this file to stop.
name: keep-awake

on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: touch the engine
        run: curl -fsS --max-time 60 https://haanji-engine.onrender.com/api/status > /dev/null
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add console/src/App.tsx console/src/pages/PackStudio.tsx console/nginx.conf render.yaml .github/workflows/keep-awake.yml
$G commit -q -F - <<'MSG'
deploy: wire the console to the engine on every host, and keep Render warm

The console's links to the demo pages were hard-coded to localhost and so
broken on the live site; they now go through /engine/, which Vite proxies
in development, Vercel rewrites in production and nginx now proxies in the
compose stack. Render learns the console's URL so the landing page can link
back. A ten-minute GitHub Actions ping stops the free instance sleeping.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 9: Visual and accessibility pass with Playwright + axe

**Files:**
- Create: `engine/tests/visual_check.py` (not collected by pytest — the name has no `test_` prefix)

**Interfaces:**
- Consumes: a running server at `http://127.0.0.1:8090`; the page ids from Tasks 3–6.
- Produces: screenshots in the scratchpad `shots/` directory and a printed report; exits non-zero on any serious/critical axe issue or horizontal overflow.

- [ ] **Step 1: Install Playwright in the venv**

Run:
```bash
$PY -m pip install -q playwright==1.47.0 && $PY -m playwright install chromium 2>&1 | tail -2
```
Expected: ends without error (a chromium download if the cached build does not match).

- [ ] **Step 2: Write the script**

Create `engine/tests/visual_check.py`:

```python
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
```

- [ ] **Step 3: Run it**

```bash
cd engine
$PY -m haanji.cli serve --port 8090 > /tmp/haanji-serve.log 2>&1 &
sleep 2
$PY tests/visual_check.py
kill %1
```
Expected: eight `shot …` lines, then `all pages: no overflow, no serious/critical axe issues`. If it prints PROBLEMS, fix the named page (common ones: a missing `aria-label`, a contrast pair under 4.5:1 — adjust to a token with more contrast, an element wider than the viewport on mobile — add `min-width: 0` / `flex-wrap`) and re-run until clean.

- [ ] **Step 4: Look at every screenshot**

Open each PNG in `.superpowers/shots/` (the Read tool renders images). Check against the spec with a designer's eye: the hero's phone frame has the double rule; the repair stroke is visible through the struck word; stamps are rotated and red-bordered; chalk sections read as the wall under the board; nothing is clipped at 390 px; the `/talk` engine panel is a bottom sheet on mobile. Fix anything that reads wrong, re-run Step 3, re-check.

- [ ] **Step 5: Commit**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
G=/Library/Developer/CommandLineTools/usr/bin/git
$G add engine/tests/visual_check.py engine/haanji/web/
$G commit -q -F - <<'MSG'
test(web): a visual and accessibility pass you can run by hand

Playwright screenshots of every page at desktop and phone widths, an
overflow check, and axe-core at WCAG 2 A/AA with serious and critical
issues failing the run. Not collected by pytest; it needs a browser.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
MSG
```

---

### Task 10: Ship — Docker, push, live verification

**Files:** none new.

- [ ] **Step 1: The image still builds from the root and serves the new files**

```bash
cd "/Users/aritrahazra/Desktop/Antigravity/1/Major Project-1/haanji"
docker build -q -f engine/Dockerfile -t haanji-engine:signboard . && \
docker run -d --rm --name hj-sign -e PORT=10000 -p 10000:10000 haanji-engine:signboard && \
until curl -fsS -o /dev/null http://localhost:10000/api/status; do sleep 2; done && \
curl -sI http://localhost:10000/static/signboard.css | grep -i content-type && \
curl -s http://localhost:10000/ | grep -c "hero-call" && \
docker rm -f hj-sign
```
Expected: `content-type: text/css; charset=utf-8` and `1`.

- [ ] **Step 2: Push**

```bash
G=/Library/Developer/CommandLineTools/usr/bin/git
$G -c credential.helper='!gh auth git-credential' push
```
Expected: `main -> main`. Render rebuilds the engine (~5 min); Vercel rebuilds the console (~1 min). CI runs: engine, core-api, console.

- [ ] **Step 3: Verify live**

```bash
until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 https://haanji-engine.onrender.com/static/signboard.css)" = "200" ]; do sleep 20; done
curl -sI https://haanji-engine.onrender.com/static/signboard.css | grep -i content-type
curl -s https://haanji-engine.onrender.com/ | grep -o '<title>[^<]*' 
curl -s https://haanji-engine.onrender.com/api/status | grep -o '"console_url":"[^"]*"'
curl -s -o /dev/null -w 'via vercel /engine/talk -> %{http_code}\n' https://haanji-kappa.vercel.app/engine/talk
curl -s -o /dev/null -w 'via vercel /engine/static/signboard.css -> %{http_code}\n' https://haanji-kappa.vercel.app/engine/static/signboard.css
gh run list -R aritra-25hazra/haanji --limit 2
```
Expected: `text/css`; the new title; `"console_url":"https://haanji-kappa.vercel.app"`; both Vercel lines `200`; the latest CI run `success` (or `in_progress` — wait and re-check).

Then open `https://haanji-engine.onrender.com/talk` in Chrome and run the three-line call from Task 4 Step 5 once more, on the live site.
