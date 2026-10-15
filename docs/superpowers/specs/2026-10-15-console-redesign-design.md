# Console redesign — "Register on the wall"

**Date:** 2026-10-15
**Scope:** the React console (`console/`) — its visual system, its seven pages,
and where its data comes from — plus one small engine endpoint. The demo pages
(`engine/haanji/web/`) are done and unchanged except where noted.

## 1. Decisions

| Decision | Choice | Reason |
|---|---|---|
| Surface | **C · chalk workspace, cobalt top bar, register lines** | The owner's all-day screen should be light; the board (cobalt) becomes the top bar; tables read like the appointment register on a clinic desk. Same tokens as the demo pages, so one brand with two surfaces. |
| Data | **Engine-first** | The engine is what is deployed; the console should show real calls from it. Fixtures remain only as a clearly labelled fallback when the engine cannot be reached. The core-api token path (`/api/v1`) leaves the console; core-api stays in the compose stack for its own purpose. |
| Navigation | Top bar, no sidebar | More width for registers and transcripts; one layout works from 390 px up (the nav row scrolls sideways). |
| Pack | A global chooser in the top bar | Every page is per-pack on the engine; the chooser replaces the hard-coded "Smile Care Dental". Remembered in `localStorage`. |
| Lexicon | New engine endpoint `GET /api/lexicon` | The console's lexicon page was pure fixture; the engine already builds the lexicon per pack, so expose it, and let the page probe a heard phrase. |

## 2. Design system (console)

`console/src/signboard.css` replaces `styles.css`. It carries the same tokens as
the engine's `signboard.css` (`--cobalt --cobalt-deep --marigold --chalk --ink
--haze --sindoor --leaf --sindoor-ink --leaf-ink`, fonts, motion, radii) plus
light-surface tokens: `--paper #FFFFFF` (cards), `--rule rgba(27,59,140,.14)`
(register lines), `--ink-2 rgba(20,33,61,.68)` (secondary text),
`--marigold-ink #8A6100` (marigold as text on chalk). Pages never use raw hex.

Fonts: Bricolage Grotesque (headings, tile numbers), Yatra One (हाँजी in the
wordmark), Instrument Sans (body), JetBrains Mono (numbers, codes, keys, times).
Loaded in `console/index.html` from Google Fonts with `display=swap`.

Components (all in the stylesheet; React wrappers in `components/Common.tsx`):

- **Top bar** — 64 px, cobalt, sticky. Wordmark · nav (`Aaj · Calls · Pramaan ·
  Bhasha · Packs · Studio`, active = chalk 14 % tint) · pack `<select>` · a
  `● LIVE` chip (leaf) or `SAMPLE` chip (haze) · `Talk ↗` link to `/engine/talk`.
  Below 720 px the nav scrolls horizontally; the wordmark drops the Devanagari.
- **Tile** — paper, 3 px marigold left rule, label 12 px uppercase `--ink-2`,
  value 30 px display cobalt (mono for ms/₹), foot 13 px. Numeric values count
  up over 400 ms on mount (`--ease-out`), instantly under reduced motion.
- **Panel** — paper, 1 px rule border, radius 12, header with title + hint.
- **Register** — the signature. A table whose rows are ruled (`1px --rule`
  bottom borders, 44 px rows), a 2 px faded sindoor **margin line** down the
  left of the table like a register's red margin, headers 12 px uppercase
  `--ink-2` under a 2 px cobalt rule, numbers/codes/times in mono. Wrapped in a
  horizontally scrolling container on narrow screens.
- **Chip** — 13 px/600, pill: default cobalt tint, `ok` leaf-ink tint, `warn`
  marigold-ink tint, `bad` sindoor-ink tint, `muted` ink-2. Outcome chips:
  BOOKED ok · FAQ_ANSWERED default · LEAD_CAPTURED warn · HANDED_OFF bad ·
  ABANDONED/IN_PROGRESS muted — label text is the lower-cased word with
  underscores removed.
- **Stamp**, **painted repair**, **chain**, **bubble**, **button**, **input**,
  **banner**, **empty state** — the demo pages' components on a light surface:
  stamp chalk/sindoor-ink (leaf-ink for VALID), repair struck word `--ink-2`
  with a cobalt stroke and the corrected word in cobalt, agent bubble paper with
  rule border, caller bubble marigold 25 % tint with ink text, primary button
  marigold/cobalt, ghost cobalt border, danger sindoor-ink, inputs paper with
  rule border and 44 px height, banner marigold 18 % tint with ink text.
- **Reveal** — rows and tiles fade/translate in with a 30 ms stagger on first
  render (`--i` index); none under reduced motion.
- Focus ring: 3 px cobalt on the chalk surface, 3 px marigold inside the top bar.

Contrast (checked): ink on chalk 13.9:1 · ink-2 on chalk 7.6:1 · cobalt on paper
8.6:1 · marigold-ink on chalk 5.1:1 · leaf-ink on chalk 5.8:1 · sindoor-ink on
chalk 5.4:1 · chalk on cobalt 11.2:1.

## 3. Data layer

`console/src/engine.ts` replaces `api.ts` and `live.ts`. Every call goes to
`/engine/<path>` (Vite proxies it in development, Vercel rewrites it in
production, nginx proxies it in the compose stack).

```
engine.status()                       → Status | null      (null = unreachable; 4 s timeout)
engine.insights(pack)                 → Insights
engine.calls(pack)                    → { conversations: CallRow[] }
engine.call(pack, id)                 → CallRow
engine.export(pack)                   → Export
engine.lexicon(pack, probe?)          → Lexicon
engine.packs()                        → { packs: PackSummary[] }
engine.packYaml(id)                   → { pack_id, yaml }
engine.validate(yaml)                 → { ok, problems }
engine.save(id, yaml)                 → { ok, problems, backup }       (PUT)
engine.selftest(id)                   → { ok, results[], summary }     (POST)
parseTurns(turns_json) → Turn[]       tolerant: malformed JSON → []
parseReceipts(receipts_json) → string[]
fmtMs(ms) → "<1 ms" | "22 ms" | "—"
tamper(export) → { edited, seq }      the same one-field edit the verifier page makes
verifyExport(export) → Verdict        loads /engine/static/nacl-fast.min.js and verifier.js once, then PramaanVerifier.verifyChain
```

Types live in `console/src/types.ts` and mirror the engine's JSON exactly
(`CallRow` is the `calls` table row; `Turn` is one element of `turns_json`;
`Export` is `/api/receipts/export`; `Lexicon` is the new endpoint).

`console/src/sample.ts` replaces `mock.ts`: the same shapes, built from the
README's demo call (five calls, one with the full transcript and receipt
`2504-7863`), insight numbers from the benchmark, five packs, a dozen lexicon
entries. Used only when `engine.status()` is null.

`console/src/state.tsx` — `AppProvider` / `useApp()`: `{ status, online,
checked, pack, setPack, packs, refresh }`. Checks status on mount and every 20 s
while offline; `pack` persists to `localStorage["haanji.pack"]` and falls back
to the engine's default pack if the stored one is not installed.

## 4. Pages

Every page: `<Page title sub>` renders the h1, the sub line, and — when
`checked && !online` — the banner *Engine se connect nahi ho pa raha — sample
data dikha raha hoon. Thodi der mein dobara try karo.* Loading states are a
single `Loading…` line; errors say what failed and offer **Dobara try karo**.

1. **Aaj** (`/dashboard`) — tiles: calls today (foot: total), bookings (foot:
   ₹ revenue), missed calls recovered/total, ₹ per call (foot: vs receptionist),
   words repaired, speculation hit rate (foot: hits of started). Panel *Calls
   through the day*: recharts bar chart of `by_hour` — calls cobalt, booked
   marigold, grid lines `--rule`, 260 px. Panel *How calls ended*: one stacked
   horizontal bar of `outcomes` with a legend (outcome chip colours). Panel
   *What the engine noticed*: the `insights` sentences. Refreshes every 5 s
   while online; the header hint shows the `generated_at` time.
2. **Calls** (`/calls`) — register: time (mono HH:MM), channel, caller (mono,
   `—` when null), outcome chip, repairs, spec hits, latency p50 (mono, via
   `fmtMs`). Row click → `/calls/:id`. Empty: *Abhi koi call nahi — /talk pe
   ek call karke dekho* with a button to `/engine/talk`.
3. **Call** (`/calls/:id`) — tiles: outcome, words repaired, receipt (stamp or
   `—`). Panel *Transcript*: for each turn a caller bubble (`heard`; painted
   repairs beneath when `corrections` is non-empty) then an agent bubble
   (`said`; chips for tools — `ok` with a bolt when in `speculation_hits`,
   `bad` with a shield for `guard` — and the mono latency). Panel *Receipts*:
   one stamp per code in `receipts_json`, with *Verify →* to `/ledger`.
4. **Pramaan** (`/ledger`) — loads the export, verifies it in the browser,
   shows the verdict as a stamp (VALID leaf / BROKEN sindoor with the reason),
   the chain strip (blocks turn sindoor from the first broken seq), the public
   key in mono, and a register of receipts (seq, action, code, verdict,
   reason). Buttons: **Dobara verify karo**, **Ek field chhedo aur dobara check
   karo** (client-side only; a note says so). In sample mode the page shows
   the sample receipts and *Verification needs the live engine* instead of a
   verdict.
5. **Bhasha** (`/lexicon`) — a probe box at the top: *Jo suna gaya wo likho* →
   after 300 ms the engine returns the sound key and matching entries; the
   result reads *"rut kanal" → RTKNR → root canal*. Below, a register of
   entries: word, type chip, also-heard-as, sound keys (mono), weight. A short
   panel restates the two conditions for a repair. In sample mode the probe is
   disabled with the hint *live engine chahiye*.
6. **Packs** (`/packs`) — register of installed packs (name + version,
   language, services, staff, scenarios, health chip) with an **in use** chip
   on the selected pack and **Use** buttons on the others (sets the global
   pack). Panel *What a pack contains* kept.
7. **Studio** (`/studio`) — same behaviour as today (open, edit YAML,
   validate, validate & save, run scenarios), restyled: pack register with
   health chips, a mono editor with a cobalt rule, buttons in the system,
   messages as chips, scenario results as a register with pass/fail chips.
   Needs the engine; in sample mode it shows the empty state *Pack Studio live
   engine ke bina kaam nahi karta — ye files ko sach mein badalta hai.*

## 5. Engine change

`GET /api/lexicon?pack=<id>&probe=<text>` →

```json
{ "pack": "dental_clinic", "version": 3,
  "entries": [{ "surface": "root canal", "entry_type": "SERVICE",
                "variants": ["rut kanal"], "keys": ["RTKNR"], "weight": 1.25 }, …],
  "probe": { "text": "rut kanal", "key": "RTKNR", "matches": ["root canal"] } }
```

Built with `TenantLexicon.build(version=pack.version, **pack.lexicon_seed())`,
exactly as the pipeline and the CLI build it. `probe` is present only when the
query parameter is. Unknown pack → 404.

## 6. Quality floor

Landmarks (`header`, `nav`, `main`); one h1 per page; every control ≥ 44 px;
body 16 px; visible focus; `prefers-reduced-motion` disables count-up, stagger,
stamp and stroke animations; no horizontal page scroll at 390 px (registers
scroll inside their wrapper); charts have a text summary in the panel hint; the
offline banner has `role="status"`.

## 7. Tests and verification

- Engine: `test_web.py` gains a test for `/api/lexicon` (entries present, every
  entry has keys, `probe=rut kanal` matches `root canal`).
- Console: `vitest` (node, no DOM) over the pure parts of `engine.ts` —
  `enginePath`, `parseTurns` (valid, malformed, missing fields), `parseReceipts`,
  `fmtMs`, `tamper`.
- `npm run build` type-checks under `strict`.
- `engine/tests/visual_check.py` gains a `CONSOLE_BASE` mode that screenshots
  the six console routes (plus a call detail when a call exists) at desktop
  and phone widths with the same overflow and axe checks.
- Live: after deploy, the Vercel console's dashboard shows the Render engine's
  real numbers and `/calls` lists the calls made during verification.

## 8. Files

```
console/index.html                    fonts, title
console/src/signboard.css             replaces styles.css
console/src/types.ts                  rewritten to the engine's shapes
console/src/engine.ts                 new; replaces api.ts + live.ts
console/src/sample.ts                 replaces mock.ts
console/src/state.tsx                 new
console/src/components/Common.tsx     rewritten
console/src/App.tsx, main.tsx         top bar, provider
console/src/pages/*.tsx               seven pages rewritten
console/src/engine.test.ts            new
engine/haanji/server.py               /api/lexicon
engine/tests/test_web.py              one test
engine/tests/visual_check.py          console mode
```

Removed: `console/src/api.ts`, `live.ts`, `mock.ts`, `styles.css`.

## 9. Non-goals

Authentication; the core-api data path; editing packs as forms; dark mode for
the console; new engine analytics.
