# HaanJi — 90-second demo video script

Record with Loom or QuickTime at 1440×900, Chrome, mic allowed. Speak Hinglish or
English — whichever is natural; the on-screen text carries the detail. Pause the
hero on the landing page by hovering so it does not distract while you talk.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:08 | Landing page, hero call playing. Hover to pause it at the stamp. | "HaanJi ek AI receptionist hai Indian clinics, salons aur labs ke liye. Phone uthata hai, Hinglish mein baat karta hai, booking karta hai — aur baad mein saabit kar sakta hai ki caller ne kya haan boli." |
| 0:08–0:14 | Scroll to the three pillars. Point at the three numbers. | "Teen cheezein isme nayi hain, aur teeno napi hui hain — ye numbers README ke benchmark se aate hain, andaaza nahi." |
| 0:14–0:20 | Click **Baat karke dekho**. On `/talk`, click **Start call**. | "Chaliye, call karte hain. Ye browser ka mic use karta hai — koi API key nahi." |
| 0:20–0:35 | Speak (or type) `haan ji mujhe rut kanal karwana tha`. Let the repair paint. Point at the Bhasha card. | "Maine jaan-boojh ke 'rut kanal' bola — recogniser ne galat suna. Bhasha Bridge ne usse 'root canal' padha, kyunki dono ka sound-key same hai aur recogniser khud sure nahi tha. Dono conditions chahiye — warna ye layer galat corrections karti." |
| 0:35–0:48 | Say `kal subah ka time mil jayega`. Point at the Speculation card. | "Jab main bol hi raha tha, engine ne availability pehle se check kar li — speculative execution, jaise CPU branch predict karta hai. Jawab tab use hota hai jab asli sawaal byte-by-byte wahi nikle." |
| 0:48–1:02 | `haan theek hai confirm kar do` → `Vijay Sharma 9876543210` → `haan confirm kar do`. Watch the stamp land; point at the Pramaan chain. | "Booking confirm. Aur ye receipt — isme wo exact sentence hai jo agent ne poocha, aur exact shabd jo maine bole, Ed25519 se signed, pichhli receipt se chained. Bina confirmation ke ledger write accept hi nahi karta." |
| 1:02–1:18 | Open `/verify`. Click **Is server ka export load karo** — VALID stamp. Click **Ek field chhedo aur dobara check karo** — BROKEN, chain turns red. | "Aur koi bhi ise verify kar sakta hai, browser mein, humpe bharosa kiye bina. Ek field badlo — chain wahin toot jaati hai." |
| 1:18–1:28 | Open the console (https://haanji-kappa.vercel.app). Show the dashboard and Pack Studio for two seconds each. | "Owner ke liye dashboard, aur Pack Studio — ek YAML file se naya business type onboard hota hai. Paanch packs already hain, ek Benglish mein." |
| 1:28–1:30 | Back to the landing page. | "Open source hai, link description mein. Dhanyavaad." |

## Before you record

- Open https://haanji-engine.onrender.com once two minutes earlier so it is warm.
- Chrome, not Safari — the mic needs Web Speech.
- Keep the engine panel visible; it is the part evaluators remember.
- One take is fine. Mistakes are fine. Do not re-record for polish.

## After

Upload (YouTube unlisted or Loom), then put the link in the README under
"See it live" — the placeholder line is already there.

## Demo day: WhatsApp live (Fri 18 Dec 2026)

### The day before (17 Dec)

1. Add the examiner's number. In Meta, open the Haanji app → Use cases →
   WhatsApp → Customize → API Setup → **To** → *Manage phone number list*, and
   enter their WhatsApp number with +91. Meta sends them an OTP on WhatsApp, so
   ask for the number a day early. The test number answers at most 5 numbers;
   remove an old one if the list is full.
2. Plan the token. The temporary token lasts 24 hours. Unless you have made a
   permanent system-user token, generate a new one on the morning of the demo
   (API Setup → *Generate access token*), paste it into Render → `haanji-engine`
   → Environment → `HAANJI_WA_TOKEN`, and save. The engine restarts in 1–2
   minutes.
3. Leave `main` alone on demo day. Render redeploys on every push: the engine
   goes down for 1–2 minutes and loses its bookings and receipts.
4. The dental pack is closed on Sundays. On a Friday, "kal" means Saturday and
   books fine; if the demo moves to a Saturday, ask for another day, because a
   Sunday request ends as a lead instead of a booking.

### Five minutes before

5. Open https://haanji-engine.onrender.com/api/status to wake the free Render
   instance, and wait for `"whatsapp": {"configured": true, …}`.
6. From your phone, send `hi` to the test number. A greeting back means
   WhatsApp works.
7. Keep three Chrome tabs open: `/talk`, `/verify`, and the console on Calls
   and Pramaan.

### If something breaks

8. WhatsApp stays silent (expired token, number not on the list, Meta outage):
   switch to `/talk` and click the "Ye boliye" lines. The browser call runs on
   the same engine, and its receipt opens on `/verify` like a WhatsApp one.
9. Render is down: on the laptop, run `cd engine && .venv/bin/haanji serve` and
   open http://localhost:8090/talk.
