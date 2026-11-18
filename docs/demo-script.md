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

## Demo day (Fri 18 Dec 2026): WhatsApp through the simulator

**Where real WhatsApp stands (checked 2026-11-18).** The engine side works end
to end:
- a message to the test number reaches the engine;
- HaanJi answers it;
- Meta accepts the reply.

Meta then refuses to deliver it: `/api/status` → `whatsapp.last_send.delivery`
shows **131031 "Business account locked"**. The Haanji business portfolio is not
verified, and Meta now restricts messaging until it is. Verification needs a
legally registered business and its documents.

So on demo day, WhatsApp is shown with HaanJi's own simulator. It is the same
engine, the same booking flow and the same receipts; only Meta's delivery is
left out. Say so plainly if asked.

### Five minutes before

1. Open https://haanji-engine.onrender.com/api/status to wake the free Render
   instance (about a minute).
2. Keep four tabs open:
   - `/whatsapp`, the WhatsApp simulator;
   - `/talk`, the browser call;
   - `/verify`;
   - the console on Calls and Pramaan.
3. Leave `main` alone on demo day. Render redeploys on every push; the engine
   goes down for a minute or two and loses the demo's bookings.
4. The dental pack is closed on Sundays. On a Friday, "kal" means Saturday and
   books fine.

### The WhatsApp part (2 minutes)

5. In `/whatsapp`, type a 10-digit number and chat:
   - "kal subah teeth cleaning karwani hai"
   - pick a slot
   - give a name
   - "haan"

   The reply carries the receipt link. Open it on `/verify`, then show the same
   booking in the console under Calls and in Pramaan.

### When a teacher wants to book from their own phone

Show the QR code (`docs/media/qr-talk.png` for the call, `docs/media/qr-whatsapp-simulator.png` for the chat) or say the link.

- **Call (`/talk`).** They type their own 10-digit number in the number box and press the mic. Chrome on Android hears speech; on an iPhone, typing is the safe way. They then:
  - say or type "kal subah teeth cleaning karwani hai";
  - pick a slot;
  - give their name;
  - say "haan".
- **Chat (`/whatsapp`).** The same flow, typed: their number at the top, then they chat as on WhatsApp.

While they do it, keep the console on the laptop open on Calls or the Calendar: their booking appears there within a second. The confirmation code opens the signed receipt on `/verify`. On the public demo their number is shown masked, and no real WhatsApp is sent to it.

### If something breaks

6. Render is down: on the laptop, run `research/collect/session.sh start` and
   use http://localhost:8090/whatsapp and /talk.

### Real WhatsApp later

When a registered business can be verified (Business Settings → Security
Center → Business verification), the same token, number and webhook start
delivering, with no code change.
