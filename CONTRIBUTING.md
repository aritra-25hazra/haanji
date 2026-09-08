# Contributing — how three people build HaanJi on their own machines, on their own time

HaanJi is built by **Aritra Hazra, Prabhav Upadhayay and Anuj Uniyal**. We do
not share a computer and we do not work at the same hours — one of us codes at
8 in the morning, another after dinner. That is normal for every software team
on earth, and the answer to "how?" is the same everywhere: **the project does
not live on anyone's laptop. It lives in the git repository.** Each laptop
holds a clone; git merges the work.

This file is the contract that makes that painless.

---

## 1. Every machine runs the whole project

Nothing in HaanJi needs a shared server, an API key, or anyone else's machine
to be switched on. Setup on a fresh Mac/Windows/Linux laptop:

```bash
git clone <repo-url> haanji && cd haanji/code

# Python engine (3.11+)
cd engine
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev,web]"
pytest -q                    # 161 tests — your clone is healthy
python -m haanji.cli serve   # your own http://localhost:8090

# Console (Node 18+), separate terminal
cd ../console
npm install && npm run dev   # your own http://localhost:5173
```

Local state (`engine/var/` — SQLite, ledger keys) is **gitignored**: every
developer has their own throwaway data, seeded by `demo`/`selftest`, so nobody
can corrupt anybody else's database, because there is no shared database.

## 2. Branches, not turns

Nobody waits for anybody. `main` is protected — no direct pushes. All work
happens on short-lived branches pushed to the shared remote (GitHub):

```bash
git checkout main && git pull          # start from everyone's latest work
git checkout -b feat/wa-retry          # yours alone; nobody can conflict with you here
# ...commit early, commit often...
git push -u origin feat/wa-retry       # open a Pull Request
```

A branch is merged only when (1) one other member has reviewed it, and
(2) the gate passes:

```bash
make test      # pytest + selftest — green or it does not merge
```

The same gate runs in CI (`.github/workflows/ci.yml`), so a review at midnight
and a merge at 8 am need no meeting.

Branch names: `feat/…`, `fix/…`, `docs/…`, `bench/…`. Commit messages say what
changed and why in one line; the diff says how.

## 3. Component owners

Three people editing the same file at the same time is the only way git hurts,
so the codebase is split into areas with a first owner. Owner means *first
reviewer and tie-breaker*, not exclusive author — everyone works everywhere.

| Area | Paths | Owner |
|---|---|---|
| Voice engine core — pipeline, speculation, adapters, web call | `engine/haanji/pipeline.py`, `speculation/`, `adapters/`, `web/talk.html`, `server.py` sessions | Aritra Hazra |
| Language & channels — Bhasha Bridge, NLU, packs, WhatsApp, missed-call | `engine/haanji/bhasha/`, `nlu.py`, `speak.py`, `channels/`, `packs/` | Prabhav Upadhayay |
| Trust & surfaces — Pramaan ledger, verifier, console, Pack Studio, Core API | `engine/haanji/pramaan/`, `web/verify.html`, `console/`, `core-api/` | Anuj Uniyal |

Cross-cutting files (`models.py`, `policy.py`, `tools/`, this file) belong to
everyone: touching one means saying so in the group chat *before* pushing, and
such PRs get two reviewers instead of one.

## 4. The weekly integration ritual

Async work still needs one synchronous habit. Once a week, together (in person
or on a call):

1. `git pull`, run `make test` and `python -m haanji.bench` on one machine;
2. read the new numbers in `research/results.json` against the README's claims;
3. demo whatever merged that week from `/talk`, `/whatsapp` or the console;
4. pick the next week's branches so no two people need the same file.

Fifteen minutes; it has caught every drift before it became a merge conflict.

## 5. Definition of done for any PR

* Tests exist for the change (a bug fix adds the test that would have caught it).
* `make test` green locally and in CI.
* If a measured number moved, `research/results.json` is regenerated and the
  README table updated in the same PR — claims and code never diverge.
* If a pack changed, its `scenarios:` still pass (`haanji selftest --pack …`),
  because scenarios are a pack's shipping test, not documentation.
* No secrets, no `var/`, no generated files in the diff.

## 6. FAQ we actually get

**"But the project runs on Aritra's Mac?"**
A copy of it does. `git clone` puts an equal, fully-runnable copy on any
machine in two minutes — engine, server, console, benchmarks, all offline. The
Mac has no special role; if it fell into the Narmada tomorrow, `main` on the
remote is the project and nothing is lost but uncommitted work.

**"What if two of us edit the same line?"**
Git flags it as a conflict in the later PR; the two authors resolve it looking
at both diffs, and the component table above makes it rare in the first place.

**"How do we try each other's unfinished work?"**
`git fetch && git checkout feat/their-branch` — run it locally, comment on the
PR, switch back. Nobody's half-done work ever blocks anyone, because it is on
a branch, not on `main`.
