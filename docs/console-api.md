# Console API (engine `/api/*`)

Everything the owner console needs, served by the engine. Paths are relative to
the engine (the console reaches them through the `/engine/` rewrite). With
`HAANJI_AUTH=on`, every route below needs a bearer token; **owner** routes need
the owner role, the rest need **staff**. `?pack=` is always required when it is
listed; omitting it never means "every pack".

## Bookings (the calendar)

| route | role | what |
|---|---|---|
| `GET /api/bookings?pack&from=YYYY-MM-DD&to=YYYY-MM-DD&status=` | staff | bookings in the range (inclusive), oldest first. `status` is `CONFIRMED` (default), `CANCELLED`, `NO_SHOW`, `COMPLETED` or `ALL`. |
| `POST /api/bookings/{booking_id}/cancel?pack` | staff | cancels from the console. Sealed in the ledger as `staff_cancel` with who did it. |
| `POST /api/bookings/{booking_id}/status?pack` body `{"status": "NO_SHOW" \| "COMPLETED" \| "CONFIRMED"}` | staff | marks attendance. Sealed as `staff_update`. |
| `GET /api/bookings/{pack}/{booking_id}.ics` | public | one booking as a calendar file (unchanged). |

A booking row:

```json
{"booking_id": "…", "service": "root canal", "staff": "Dr Sheikh", "date": "2026-10-30",
 "time": "09:30", "duration_min": 60, "customer_name": "Vijay Sharma", "phone": "9876543210",
 "status": "CONFIRMED", "receipt_code": "2504-7863", "created_at": "…",
 "paid": false, "deposit_inr": 500, "payment_link": null, "reminder_sent_at": null}
```

Staff see the phone masked (`…3210`); owners see it whole.

## Customers

| route | role | what |
|---|---|---|
| `GET /api/customers?pack&q=` | staff | one row per number: `phone`, `name`, `last_service`, `last_visit`, `visits`, `bookings` (confirmed count), `no_shows`. `q` filters by name or last digits. |
| `GET /api/privacy/customer/{phone}?pack` | owner | everything held about one number (unchanged). |
| `DELETE /api/privacy/customer/{phone}?pack` | owner | right to erasure (unchanged; needs all ten digits). |

## Settings (per pack)

| route | role | what |
|---|---|---|
| `GET /api/settings?pack` | staff | the pack's settings, with defaults filled in. |
| `PUT /api/settings?pack` | owner | partial update; unknown keys are rejected (422). |

```json
{"reminders_on": true, "reminder_hour_ist": 18, "reminder_day_before": true,
 "deposit_inr": 0, "waitlist_on": true, "digest_hour_ist": 20,
 "language_script": "latin"}
```

`deposit_inr > 0` makes every new booking carry a payment link (see Payments).

## Waitlist

| route | role | what |
|---|---|---|
| `GET /api/waitlist?pack` | staff | people waiting for a day/service: `entry_id`, `phone`, `name`, `service`, `date`, `period`, `created_at`, `offered_at`, `status` (`WAITING`, `OFFERED`, `BOOKED`, `EXPIRED`). |
| `DELETE /api/waitlist/{entry_id}?pack` | staff | remove an entry. |

The engine fills the list itself: when a day has no slot and the caller leaves
a number, the lead is also a waitlist entry; when a booking on that day is
cancelled, the first waiting person is messaged on WhatsApp with the freed slot.

## Payments

| route | role | what |
|---|---|---|
| `GET /api/payments?pack` | staff | payment links issued: `payment_id`, `booking_id`, `amount_inr`, `status` (`CREATED`, `PAID`, `FAILED`, `EXPIRED`), `link`, `created_at`, `paid_at`. |
| `POST /payments/razorpay/webhook` | signed | Razorpay's webhook (`X-Razorpay-Signature`). A paid link marks the booking paid and seals `payment_received`. |

Without `HAANJI_RAZORPAY_KEY_ID`/`_KEY_SECRET`, links are mock links on this
server (`/pay/{payment_id}`) that a demo can "pay" with one click.

## Users (unchanged)

`GET/POST /api/auth/users`, `DELETE /api/auth/users/{phone}` (owner);
`POST /api/auth/logout` revokes the caller's tokens; `GET /api/auth/me`.

## Outcomes

A call's `outcome` is one of `BOOKED`, `RESCHEDULED`, `FAQ_ANSWERED`,
`LEAD_CAPTURED`, `HANDED_OFF`, `REFUSED`, `ABANDONED` (and `IN_PROGRESS` for a
live one). `REFUSED` is new in 1.1: the agent declined (advice, a promise, a
discount) and the caller did not go on to anything else.

## Ops counters

`GET /api/ops?pack` (staff) carries `counters.unconfirmed_refused`: how many
writes the ledger refused for lack of a confirmation proof. The console shows
that number, not a constant.
