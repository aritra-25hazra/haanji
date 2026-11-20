# Security policy

## Reporting a vulnerability

Please report it privately, not in a public issue:
**Security → Report a vulnerability** on this repository
(GitHub's private vulnerability reporting).

Include:
- what an attacker can do;
- the steps or a request that shows it;
- the commit or the live URL you tested.

We aim to reply within 7 days. We fix the problem before anything about it is made public.

## Supported versions

Only the latest commit on `main` gets fixes. This is what runs at
https://haanji-engine.onrender.com and https://haanji-kappa.vercel.app.

## Scope

These are in scope:
- the engine (`engine/`);
- the console (`console/`);
- the Vertical Packs;
- the two live deployments above.

Do not attack other people's accounts, real customers' data, or the hosting
providers themselves.

## How HaanJi is secured

[docs/security.md](../docs/security.md) has the threat model and every control.
Each control is listed with the test that fails if it is removed. The ledger's
guarantees are in [docs/pramaan-security.md](../docs/pramaan-security.md).
