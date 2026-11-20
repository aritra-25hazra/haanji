# Security: what HaanJi protects, from whom, and how

This page covers sign-in, the public routes, webhooks and secrets. The
ledger's own guarantees are in [pramaan-security.md](pramaan-security.md);
customer data and the DPDP Act are in [privacy-dpdp.md](privacy-dpdp.md).
Each control below has a test, named in brackets, that fails if the control
is removed.

## What is protected, from whom

| Asset | Threat |
|---|---|
| The console (bookings, customers, settings) | someone signing in as the owner or staff |
| Customers' numbers and names | an outsider reading or exporting them |
| The shop's WhatsApp and phone line | forged webhooks making HaanJi book, or message strangers |
| Secrets (tokens, keys, passwords) | leaking through the repository, logs, URLs or `/api/status` |

Out of scope:
- a compromised Render, Vercel or Neon account;
- a stolen, unlocked phone that holds both the password manager and the authenticator app.

## Sign-in

- **Passwords** are hashed with scrypt and a salt, never stored or logged.
  A password has at least 10 characters and is not the email.
  Ten wrong passwords in 15 minutes lock that email for 15 minutes.
  An unknown email costs the same hash, so timing does not reveal it. *(test_auth_password, test_security)*
- **One-time codes** (WhatsApp or email) last 5 minutes and work once.
  At most 3 codes are issued per 15 minutes, and 10 wrong guesses lock the account.
  Only a hash of each code is kept. *(test_auth, test_login_codes)*
- **Same answer for every account.** Login, WhatsApp code, email code and reset
  answer the same for an unknown or throttled account as for a real one.
  The email goes out after the answer, so timing does not reveal an account either. *(test_security, test_login_codes)*
- **Password reset** needs a reset code (a sign-in code does not work).
  It applies the password policy, lifts the wrong-password lock, signs out every device and is written to the activity log. *(test_login_codes)*
- **Two-step sign-in** (RFC 6238, checked against the RFC's test vectors) is optional for each user:
  - Every first step stops at a 5-minute, single-use, HMAC-signed ticket. This covers the password, the email code, the WhatsApp code and Google.
  - A code works once; there is no replay inside its 30-second window.
  - 10 wrong codes lock the second step for 15 minutes.
  - There are 8 one-time recovery codes. Only their hashes are kept.
  - The app's secret is encrypted with AES-GCM, under a key derived (HKDF) from the auth secret.
  - If that secret changes, two-step fails closed and recovery codes still work. *(test_two_step)*
- **Tokens** are HMAC-signed and expire. They can be revoked per device or everywhere.
  The signing secret is `HAANJI_AUTH_SECRET` or, without it, a value kept in the auth database, so a deploy does not sign everyone out. *(test_security)*
- **The live feed** (`EventSource` cannot send headers) opens with a 60-second, single-use ticket. A long-lived token never goes in a URL. *(test_security)*
- **Rate limits.** Every write is limited per client. Sign-in routes have a tighter limit of 20 a minute per address, on top of the per-account locks. *(test_security)*

## Public routes

Every route that changes something without a signed-in user is listed, with
its reason, in `PUBLIC_WRITES` in `engine/tests/test_security.py`. A new
public write route fails that test until someone states why it is safe.

The public ones are:
- the product's own channels: a web call and the chat simulator;
- sign-in steps;
- signed webhooks;
- a customer's data request, which is proved with a code sent to their number.

On a demo server, visitors book into a "(Demo)" copy of each shop. They can
read back only their own conversation, never the list of chats.

## Webhooks

| Route | Proof required on a public server |
|---|---|
| `/wa/webhook` (Meta) | `X-Hub-Signature-256` with `HAANJI_WA_APP_SECRET`. Refused without the secret, even when Meta is not set up, so a forged delivery cannot be answered through Twilio. |
| `/wa/twilio`, `/wa/twilio/status` | `X-Twilio-Signature` with `HAANJI_TWILIO_AUTH_TOKEN`, over the public URL. |
| `/telephony/twilio/voice` | Twilio's signature. The media socket then needs a single-use ticket that expires after 2 minutes. |
| `/telephony/exotel/stream` | `?key=HAANJI_EXOTEL_STREAM_KEY`, compared in constant time. |
| `/api/telephony/missed-call` | `X-HaanJi-Secret`. |

A redelivered WhatsApp message is answered once. *(test_whatsapp_webhook, test_twilio_whatsapp, test_telephony_exotel)*

## Secrets

- Secrets live only in `engine/.env` (gitignored) or in Render's environment.
  `render.yaml` lists them as `sync: false`, so the blueprint never re-applies a value.
- `/api/status` says whether each thing is set up and how the last send went.
  It masks the recipient and never shows a key, token or password. *(test_login_codes, test_twilio_whatsapp, test_whatsapp_webhook)*
- The server's access log hides the value of `key`, `ticket`, `token`, `code`
  and `state` in URLs (the Exotel key rides in the applet's URL). *(test_telephony_exotel)*
- Pages carry a Content-Security-Policy. The console (`console/vercel.json`)
  runs scripts only from its own origin. The engine's pages allow their own
  inline scripts but load nothing from elsewhere. Neither can be framed by
  another site (`frame-ancestors 'none'`).

## Dependency audit (2026-11-20)

| What | Tool | Result |
|---|---|---|
| Console, shipped code | `npm audit --omit=dev` | 0 vulnerabilities |
| Console, dev tools | `npm audit` | 9 moderate, all in test and lint tools (`@vitest/mocker`, `minimatch` under eslint); none is in the built site. `npm audit fix` stopped with an npm error (`edgesOut`), so they remain. |
| Engine, installed packages | `pip-audit --path` | 2 found in the local environment: `opentelemetry-api` 1.45.1 (a dependency of fastapi and anthropic) and `setuptools` 84.0.0. Both were upgraded locally, and a second run found none. The Docker image installs current versions at each build; the live image was not audited. |

Run them again with:
`npm audit` in `console/`, and `pip-audit --path engine/.venv/lib/python3.11/site-packages`.

## Reporting a problem

Open a private security advisory on the GitHub repository, not a public issue.
