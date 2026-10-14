# Demo pages redesign — "Signboard"

**Date:** 2026-10-14
**Scope:** the four pages the engine serves (`/`, `/talk`, `/whatsapp`, `/verify`),
a shared design system they draw from, and the small engine/console changes that
make them work on the live hosts. The React console's own redesign is a later
project and is out of scope here.

## 1. What we decided, and why

| Decision            | Choice                                                                                                                  | Reason                                                                                                                                              |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Which surface first | Demo pages                                                                                                              | They are what a visitor sees from a shared link; first impression lives here.                                                                       |
| Visual direction    | **A · Signboard** — hand-painted Indian shop sign                                                                       | Drawn from the customer's own world (clinic, salon, lab signboards), not from any AI-product default. Bilingual lettering is native to the subject. |
| Landing hero        | **2 · the call, replayed** — split hero with a scripted call auto-playing in a phone frame                              | The product's whole argument is that it _does the thing_; the hero should show it doing the thing while the headline gives an evaluator context.    |
| `/talk` layout      | **3 · call + engine panel** — transcript on the left, a live panel showing Bhasha, Speculation and Pramaan on the right | The three research contributions are invisible today. The panel makes them observable while a call happens.                                         |
| Implementation      | **Plain HTML/CSS/JS inside the engine**, shared `signboard.css` + `signboard.js`                                        | Keeps the README's "one process is the whole platform" promise, no build step, deploys to Render unchanged. The look does not need a framework.     |
| Keep-awake          | GitHub Actions pings the engine every 10 minutes                                                                        | Removes the ~23 s cold start on the free plan. Fits in the free 750 h/month. Removable by deleting one file.                                        |

## 2. Design system — tokens

All four pages load `static/signboard.css`, which defines these as CSS custom
properties on `:root`. Pages never use raw hex.

### Colour

| Token           | Hex       | Role                                                                           |
| --------------- | --------- | ------------------------------------------------------------------------------ |
| `--cobalt`      | `#1B3B8C` | The board. Primary surface for hero, `/talk`, `/verify`, nav.                  |
| `--cobalt-deep` | `#102A66` | Recessed panels and cards sitting on the board.                                |
| `--marigold`    | `#F5B91E` | Painted lettering. Primary buttons, repairs, highlights, focus ring.           |
| `--chalk`       | `#FFF7E6` | Text on cobalt; background of "whitewashed wall" sections on the landing page. |
| `--ink`         | `#14213D` | Text on chalk sections.                                                        |
| `--haze`        | `#9FB3E8` | Muted text on cobalt (struck-through words, hints). Only at ≥14 px.            |
| `--sindoor`     | `#E2553A` | Alerts, guardrails, broken chain, "End call".                                  |
| `--leaf`        | `#8FD694` | Verified, chain intact, speculation hit.                                       |

Contrast (checked): chalk on cobalt 11.2:1 · marigold on cobalt 6.5:1 · cobalt on
marigold 6.5:1 · ink on chalk 13.9:1 · haze on cobalt 4.7:1 · sindoor on cobalt
3.4:1 (large text/icons only, always paired with a word or icon) · leaf on cobalt 8.1:1.

### Type

| Role               | Face                                 | Weights         | Used for                                      |
| ------------------ | ------------------------------------ | --------------- | --------------------------------------------- |
| Display            | **Bricolage Grotesque** (opsz 12–96) | 800             | h1, h2, wordmark "HaanJi"                     |
| Devanagari display | **Yatra One**                        | 400             | हाँजी and Hindi words inside headlines        |
| Body               | **Instrument Sans**                  | 400 / 500 / 600 | everything else                               |
| Data               | **JetBrains Mono**                   | 500             | sound keys, receipt codes, timers, ms, hashes |

Loaded from Google Fonts with `display=swap` and a `preconnect`. Fallback stacks:
display → `"Arial Black", Impact, sans-serif`; body → system sans; mono → `ui-monospace, Menlo, monospace`.

Scale (px): 12 · 14 · 16 · 18 · 22 · 28 · 40 · 56 · 80. Body 16/1.5 (never
below 16 on mobile). Display line-height 1.02, letter-spacing −0.02em.

### Space, shape, elevation

8 px grid. Section padding 96 px desktop / 56 px mobile. Content max-width 1180 px.
Radii: 8 (controls), 14 (cards), 999 (chips). No drop shadows on the board; depth
comes from `--cobalt-deep` and the painted border (below).

### Motion tokens

| Token        | Value                      | Used for                                          |
| ------------ | -------------------------- | ------------------------------------------------- |
| `--t-micro`  | 160 ms                     | hover, press, chip appear                         |
| `--t-base`   | 240 ms                     | reveal, panel open, bubble enter                  |
| `--t-paint`  | 400 ms                     | painted repair stroke, stamp landing              |
| `--ease-out` | `cubic-bezier(.2,.8,.2,1)` | anything entering                                 |
| `--ease-in`  | `cubic-bezier(.4,0,1,1)`   | anything leaving (exits ≈ 65 % of enter duration) |

`@media (prefers-reduced-motion: reduce)`: every transform animation is removed,
opacity transitions capped at 100 ms, the hero's scripted call renders its final
state immediately, the waveform is a static bar.

## 3. Signature components

**Painted repair** (`.repair`). Shown wherever Bhasha Bridge changed a word.
Markup: `<span class="repair"><s>rut kanal</s><b>root canal</b><small>0.32</small></span>`.
Animation: an inline SVG path draws a marigold brush stroke left→right across
the struck word over `--t-paint`; the corrected word then fades/translates in
beneath it (`--t-base`, 80 ms after the stroke starts). The confidence is set in
mono, haze. This is the product's core idea made visible, in the signboard's
own vocabulary.

**Stamp** (`.stamp`). Shown when a receipt is sealed. A rounded rectangle, 2 px
sindoor border, chalk fill, mono text `RECEIPT 2504-7863`, rotated −3°. Lands
with scale 1.35→1 and opacity 0→1 over `--t-paint`, ease-out, with one 60 ms
opacity dip at the moment of contact. Used in the hero call, `/talk`,
`/whatsapp`, `/verify`.

**Painted frame** (`.frame`). The double rule a signwriter paints around a board:
`box-shadow: inset 0 0 0 4px var(--marigold), inset 0 0 0 7px var(--cobalt), inset 0 0 0 8px var(--marigold)`.
Frames the hero phone and the engine panel cards.

**Chip** (`.chip`, variants `.chip-spec`, `.chip-tool`, `.chip-guard`,
`.chip-rcpt`). 13 px / 600, pill, 28 px tall; marigold tint by default, leaf
tint for speculation hits, sindoor tint for guardrails. A chip may carry one
inline SVG icon (bolt for speculation, shield for guardrail) before its text.

**Icons.** Inline SVG only, one family (Lucide-style, 1.75 px stroke, 20 px box):
phone, mic, mic-off, speaker, speaker-off, bolt, shield, lock, arrow-right,
check, x, chevron. No emoji anywhere in the interface; where the current pages
use 🎤 🔊 📵 😈 the SVG equivalent takes its place with an `aria-label`.

**Button** (`.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger`). 44 px min
height, 600 weight. Primary: marigold fill, cobalt text. Ghost: chalk 1.5 px
border. Danger: sindoor fill, chalk text. Press: scale 0.97 over `--t-micro`.
Focus-visible: 3 px marigold ring with 2 px cobalt gap.

**Reveal** (`[data-reveal]`). IntersectionObserver adds `.in` once at 15 %
visibility: opacity 0→1, translateY 12→0 over `--t-base`. Siblings stagger 40 ms
via `--i`.

**Wordmark**. `HaanJi` in display 800 + `हाँजी` in Yatra One, marigold. On page
load the wordmark paints in with a `clip-path: inset(0 100% 0 0)` → `inset(0)`
over 600 ms, ease-out.

## 4. Pages

All pages: `<header>` with nav, `<main>`, `<footer>`; one `h1`; a skip link to
`main`; `lang="hi-Latn"` on Hinglish copy blocks where it matters for screen
readers; every interactive element a real `<button>`/`<a>`; all URLs
**relative** (`api/status`, `static/signboard.css`) so the same files work at
`/talk` on the engine and at `/engine/talk` through the Vercel rewrite.

### 4.1 Landing — `/` (`index.html`)

Nav: wordmark · Demo (`talk`) · WhatsApp · Verify · GitHub (external) · a
"Console ↗" link whose href comes from `api/status` → `console_url` (hidden
until loaded).

**Hero** (cobalt). Two columns 1.1fr / 1fr, stacking below 900 px.
Left: eyebrow chip "AI receptionist · Hinglish"; h1 _Phone uthata hai.
Hinglish mein. **सबूत** ke saath._ (सबूत in Yatra One, marigold); sub _Clinic,
salon ya lab ke liye. Har call uthata hai, booking likhta hai, aur baad mein
saabit kar sakta hai ki caller ne kya haan boli._; buttons **Baat karke dekho**
(→ `talk`) and **Kaise kaam karta hai** (→ `#pillars`).
Right: the **phone frame** (`.frame`, `--cobalt-deep`), header "● LIVE CALL ·
SMILE CARE DENTAL" with a running timer, a transcript region
(`aria-live="polite"`) where `hero-call.js` plays this script in a loop:

| #   | Who    | Text                                                                                         | Effect after                                         |
| --- | ------ | -------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 1   | agent  | Haanji, Smile Care Dental. Main aapki kya madad karun?                                       | —                                                    |
| 2   | caller | haan ji mujhe rut kanal karwana tha                                                          | painted repair `rut kanal → root canal · 0.32`       |
| 3   | agent  | Theek hai. Kis din ka time dekhun?                                                           | mono `22 ms`                                         |
| 4   | caller | kal subah ka time mil jayega                                                                 | chip-spec `⚡ check_availability — pehle se taiyaar` |
| 5   | agent  | Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath. Ya phir subah saade 10 baje. Chalega? | mono `31 ms`                                         |
| 6   | caller | haan confirm kar do                                                                          | chip-tool `book_appointment`                         |
| 7   | agent  | Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath. Confirmation code 2504-7863.            | **stamp** `RECEIPT 2504-7863`                        |

Pacing: 900 ms between lines; agent lines are preceded by a 500 ms typing
indicator; after line 7 hold 2.5 s, fade the transcript out (`--t-base`), restart.
Pauses while hovered or focused; resumes on leave. Under reduced motion the
final state (all seven lines + stamp) is rendered statically. The script is
data in `hero-call.js`, not markup.

**Pillars** (chalk, `#pillars`). Three cards in a row (stack below 800 px), each a
painted badge label (not numbered — they are not a sequence), a one-line plain
explanation, the measured number from the README, and a tiny live widget:

- **BHASHA BRIDGE** — _Aapke apne catalogue se bana sound-index; recogniser ko
  bhi batata hai aur uski galti bhi sudhaarta hai — sirf tab jab wo khud sure
  na ho._ Number: **31.6 % → 1.1 %** entity errors at 30 % noise, 0 harmful
  corrections. Widget: a painted repair that re-plays every 4 s cycling through
  three real pairs (`rut kanal → root canal`, `klining → cleaning`, `sheikh →
Dr Sheikh`).
- **SPECULATIVE TURNS** — _Jab caller bol hi raha hota hai, read-only kaam pehle
  se shuru; jawab tab use hota hai jab sawaal byte-by-byte wahi nikle._ Number:
  **239 → 137 ms** median on read turns, 45.5 % hit rate. Widget: two horizontal
  bars (239 / 137) that grow on reveal.
- **PRAMAAN LEDGER** — _Har booking ek signed, chained receipt mein seal hoti hai,
  caller ki "haan" ke saath. Koi bhi, kahin bhi verify kar sakta hai._ Number:
  **80 / 80** tampering attempts caught, 0 unconfirmed writes. Widget: five
  chain blocks; on reveal the fourth turns sindoor and the links after it break.

**Try it** (cobalt). Three `.frame` cards → `talk`, `whatsapp`, `verify`, each
with a label (LIVE CALL / WHATSAPP / PRAMAAN), a title, one sentence, and an
arrow. Hover: translateY −2 px, marigold border brightens.

**Built in the open** (chalk). Three short columns: packs (_ek YAML file = ek
business type_), measured not estimated (_`python -m haanji.bench` writes
results.json_), verify it yourself (link to `verify`). Footer: open source on
GitHub · HaanJi v0.4.0.

States: `api/status` unreachable → the Console link stays hidden, nothing else
depends on the server. No loading spinner anywhere on this page.

### 4.2 Talk — `/talk` (`talk.html`)

Top bar (cobalt, 64 px): wordmark · business name (from session) · mono timer
`00:41` (starts on call start) · pack `<select>` (filled from `api/status`) ·
phone input (optional, 10 digits) · **Start call** (primary) / **Call khatam
karo** (danger, shown while on a call) · voice toggle (ghost, speaker /
speaker-off icon + "Awaaz on" / "Awaaz off").

Body: grid 1.15fr / 1fr; below 900 px the engine panel becomes a bottom sheet
with a "Engine ka sheesha ▴" toggle (collapsed by default, 44 px tap target).

**Call column.** Transcript (`aria-live="polite"`), agent bubbles chalk-tint
left, caller bubbles marigold right, enter: opacity + translateY 8 px over
`--t-base`. Caller bubble shows _what was heard_; if the turn had corrections,
a painted repair row appears under it. Agent bubble meta: chips for tools
(`.chip-spec` when speculated), guardrail, receipts (stamp, not chip), and the
mono latency. Empty state before a call: _Pack chuniye aur "Start call"
dabaiye — phir mic se boliye ya neeche type kijiye._

Interim transcript line under the transcript in haze italics (as today).

**Engine panel** (`--cobalt-deep`, three `.frame` cards, each updates on every
turn):

- **Bhasha Bridge** — last turn's corrections, each as: heard `<s>` → read
  `<b>`, then a mono line `RT·KNL = RT·KNL ✓ exact · conf 0.32`. If the turn had
  none: _Is turn mein kuch sudhaarna nahi pada._ Counter: total repairs this call.
- **Speculation** — for each tool in the last turn: name, and a 3-tick timeline
  (shuru · tayyar · poocha) with the hit/miss verdict; `⚡ hit` in leaf, `miss`
  in haze. Counter: hits / started this call.
- **Pramaan** — chain blocks (one per receipt this call, marigold; a dashed
  empty block at the end), latest receipt code in mono, "sealed · Ed25519".
  Link _Verify karo →_ to `verify`.

Bottom bar: mic button (56 px, marigold when idle, sindoor + pulse ring while
listening; a live waveform of 12 bars driven by `AnalyserNode` amplitude when
the mic is granted, otherwise by listening state), text input, **Bhejo**. The
existing Web Speech, partial-transcript and barge-in behaviour is preserved
exactly; only presentation changes.

States: `api/status` unreachable → pack select disabled, top-bar notice _Server
se connect nahi ho pa raha — thodi der mein dobara try kijiye._ Mic unsupported
→ mic button disabled with tooltip _Is browser mein mic nahi — type kijiye
(Chrome best)._ Session ended by server (`end_call`) → system line _Call khatam —
outcome BOOKED_ and the Start button returns.

### 4.3 WhatsApp — `/whatsapp` (`whatsapp.html`)

The chat canvas deliberately stays WhatsApp-like (dark green `#0B141A` /
`#005C4B` bubbles / dotted backdrop) because the demo's point is _same brain,
different channel_. Everything around it is Signboard: the sidebar and chat
header are cobalt with the wordmark, the "Simulate a missed call" button is
marigold and prominent with its explanation beneath, the thread list rows use
Instrument Sans with mono timestamps. Inside bubbles the painted repair and
stamp components are reused (recoloured to read on green). The system line for
missed-call recovery becomes a chip row with the phone-missed icon: `missed
call → HaanJi ne khud message bheja`. Empty state: _Left mein number daal ke thread kholo, ya
"missed call" dabao aur dekho HaanJi khud pehla message bhejta hai._

### 4.4 Verify — `/verify` (`verify.html`)

Cobalt page. h1 _Pramaan_ + _verifier_ (marigold). Sub as today but shorter.
Controls row: pack select · **Is server ka export load karo** (primary) ·
**Pasted JSON verify karo** (ghost) · **Ek field chhedo aur dobara check karo**
(danger, disabled until an export is loaded; a 12 px sindoor note beside it:
_sirf aapke browser mein — server pe kuch nahi badalta_).

Verdict: a large `.stamp`-styled banner — **VALID · 7 receipts · chain intact**
(leaf border/text) or **BROKEN at seq 4 · payload hash does not match** (sindoor).
It lands with the stamp animation each time a verification runs.

Chain strip: one block per receipt in a row (wrap on mobile), marigold; from the
first broken seq onward blocks turn sindoor and the connector between them is
drawn as a snapped line. Table below styled as a register: ruled rows, mono seq
and code, verdict column with word + colour (`verified` leaf, `BROKEN` sindoor,
`skipped` haze). Public key in a mono, wrapping line above the table.
"How this works" paragraph kept, moved into a chalk-tinted aside.

## 5. Shared JS — `static/signboard.js`

- `reveal()` — IntersectionObserver for `[data-reveal]`; disabled under reduced motion (elements get `.in` immediately).
- `paintRepair(el)` — builds the SVG stroke inside a `.repair` and runs its animation via the Web Animations API; returns a promise.
- `stamp(el)` — runs the landing animation on a `.stamp`.
- `typingDots()` — returns a typing indicator node.
- `timer(el)` — mm:ss ticker with start/stop.
- `waveform(canvasOrBars, analyser?)` — drives 12 bars from an `AnalyserNode`, or a gentle idle pattern when none.
- `status()` — fetches `api/status` once, caches, resolves `{packs, default_pack, console_url}` or `null`.

`hero-call.js` holds the script table from §4.1 and the loop; it only runs on
the landing page. `verifier.js` and `nacl-fast.min.js` are unchanged.

## 6. Engine and console changes

- `server.py`: `api/status` gains `console_url` from `HAANJI_CONSOLE_URL`
  (default `http://localhost:5173`); the `/static/{name}` route serves any file
  in `web/` with a MIME type from the extension (`.css` → `text/css`, `.js` →
  `text/javascript`, `.svg` → `image/svg+xml`, else as today); each entry in a
  turn's `corrections` gains `key` and `to_key` — `phrase_key()` of the heard
  and the corrected text — so the Bhasha panel can show the sound-key match
  that justified the repair; the four page routes are unchanged. No other
  engine code changes.
- `render.yaml`: add `HAANJI_CONSOLE_URL=https://haanji-kappa.vercel.app`.
- Console: `App.tsx` and `PackStudio.tsx` external links change from
  `http://localhost:8090/...` to root-relative `/engine/talk` /
  `/engine/whatsapp`, so Vite's dev proxy, the Vercel rewrite and nginx all
  resolve them from any console route; `console/nginx.conf` gains a
  `location /engine/` proxy to `engine:8090` with the prefix stripped, matching
  `vite.config.ts`. Links always include a page segment after `/engine/` — a bare
  `/engine` would make the landing page's relative URLs resolve against the
  console origin.
- `.github/workflows/keep-awake.yml`: `schedule: "*/10 * * * *"`, one step:
  `curl -fsS --max-time 60 https://haanji-engine.onrender.com/api/status`.

## 7. Accessibility and performance floor

Semantic landmarks; skip link; one h1 per page; sequential headings; visible
3 px marigold focus ring on everything focusable; all controls ≥44 px; body
≥16 px; contrast per §2; `aria-live="polite"` on transcript regions; the
transcript's repair row reads as "heard rut kanal, read as root canal" to a
screen reader (the `<s>`/`<b>` carry `aria-label`s); `prefers-reduced-motion`
honoured as in §2; `touch-action: manipulation` on buttons; no horizontal scroll
at 390 px; `min-height: 100dvh` not `100vh`.

No raster images. CSS ≤ 24 KB, JS ≤ 16 KB (excluding nacl). Fonts are the only
external requests. LCP element is the hero h1. No layout shift from the hero
phone: it has a fixed min-height; bubbles append inside a scrolling region.

## 8. Testing and verification

1. `cd engine && pytest -q` — 161 tests still pass (server.py changed).
2. `docker build -f engine/Dockerfile .` succeeds; container on `PORT=10000`
   serves all four pages and `static/signboard.css` with `text/css`.
3. Playwright (Python, in the scratchpad venv) screenshots each page at 1440×900
   and 390×844 against the local server, in light of §7: no horizontal overflow,
   fonts loaded (check `document.fonts.check`), hero loop reaches the stamp.
   Screenshots are reviewed by eye before pushing.
4. axe-core injected in Playwright on each page: zero serious/critical issues.
5. Keyboard walk on `/talk`: Tab order top bar → transcript → panel toggle →
   mic → input → send; Enter sends; Escape ends the call.
6. After push: Render deploys; re-run the live conversation check from the
   earlier session; `/engine/talk` through Vercel renders with styles.

## 9. File layout after the change

```
engine/haanji/web/
  index.html          landing (new)
  talk.html           rewritten
  whatsapp.html       rewritten
  verify.html         rewritten
  signboard.css       design system (new)
  signboard.js        shared behaviours (new)
  hero-call.js        landing hero script (new)
  verifier.js         unchanged
  nacl-fast.min.js    unchanged
.github/workflows/keep-awake.yml   new
console/src/App.tsx, console/src/pages/PackStudio.tsx, console/nginx.conf   link/proxy only
engine/haanji/server.py            console_url + MIME types only
render.yaml                        one env var
```

## 10. Non-goals

The React console's visual redesign (phase 2); any change to core-api; new
engine capabilities; a language toggle; a custom domain; replacing the WhatsApp
canvas's WhatsApp look.
