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
   instance (about a minute). While it wakes, the console shows the shape of
   each page and a seconds count instead of a blank screen.
2. Sign in to the console (https://haanji-kappa.vercel.app) with the owner's
   email and password, or with Google. Sign-in is on, so a visitor sees the
   login page; "Try the demo (no account)" opens the made-up sample shop, not
   the live bookings.
3. Keep four tabs open:
   - `/whatsapp`, the WhatsApp simulator;
   - `/talk`, the browser call;
   - `/verify`;
   - the console, signed in, on Calls and the Calendar.
4. Leave `main` alone on demo day. Render redeploys on every push and the
   engine goes down for a minute or two. Bookings are kept (they live in the
   Postgres database), but a call in progress is cut.
5. The demo shop is **Smile Care Clinic** (six departments, 13 doctors); the
   coaching shop is **Pragati Classes** (boards, JEE, NEET). The clinic is
   closed on Sundays: on a Saturday, "kal" has no slot and becomes a lead.
   Visitors book into the "(Demo)" copy of each shop; in the console, pick
   "Smile Care Clinic (Demo)" to see a teacher's booking.

### The WhatsApp part (2 minutes)

6. In `/whatsapp`, type a 10-digit number and chat:
   - "kal subah teeth cleaning karwani hai"
   - pick a slot
   - give a name
   - "haan"

   The reply carries the receipt link. Open it on `/verify`, then show the same
   booking in the console under Calls and in Pramaan.
7. Missed-call recovery: type a number and press **Simulate a missed call**.
   HaanJi writes the first WhatsApp message itself; if the chat ends in a
   booking, the missed call counts as recovered on the dashboard. Nothing is
   sent to a real WhatsApp from the simulator.

The simulator's top note says "Meta test number: not for the public yet". If
asked, that is the business-verification lock described above.

### Real WhatsApp through the Twilio Sandbox (once it is set up)

When `/api/status` shows `whatsapp.provider: "twilio"`, a teacher can use
their own WhatsApp:

1. Open `/whatsapp` on the projector: the top note shows the Sandbox number,
   the join phrase, an "Open WhatsApp" button and a QR.
2. The teacher scans the QR (WhatsApp opens with the join phrase typed in)
   and sends it, then writes "Namaste".
3. They book as in the simulator. The booking lands in "Smile Care Clinic
   (Demo)"; open that shop in the console to show it.

Say plainly that it is Twilio's test number: a phone joins once and must join
again after three days, and replies work within 24 hours of the person's last
message. Set this up a day before and test it from your own phone.

### When a teacher wants to book from their own phone

Show the QR code (`docs/media/qr-talk.png` for the call, `docs/media/qr-whatsapp-simulator.png` for the chat) or say the link.

- **Call (`/talk`).** They type their own 10-digit number in the number box and press the mic. Chrome on Android hears speech; on an iPhone, typing is the safe way. They then:
  - say or type "kal subah teeth cleaning karwani hai";
  - pick a slot;
  - give their name;
  - say "haan".
- **Chat (`/whatsapp`).** The same flow, typed: their number at the top, then they chat as on WhatsApp.

Neither page needs an account, even with sign-in on: a visitor can chat and read back only their own conversation, never anyone else's or the list of chats.

While they do it, keep the console on the laptop signed in and open on Calls or the Calendar: their booking appears there within a second. The confirmation code opens the signed receipt on `/verify`. No real WhatsApp is sent to the number they typed.

### The token queue (2 minutes)

1. In the console, open **Queue** (pick "Smile Care Clinic (Demo)" if the
   booking was made by a visitor). Today's booked patients are listed under
   "To check in".
2. Press **Check in**: the patient gets a token such as `GP-01`. Add a
   **Walk-in** for another doctor.
3. Open the waiting-room screen (the button on the Queue page, or
   `/engine/queue`) on a second screen or phone: it shows the token, never a name.
4. Press **Next patient**: the screen flashes the new token.
5. In `/whatsapp`, from the patient's number, type `mera number kab aayega`:
   HaanJi answers with the token, how many are ahead and a rough wait.

### If something breaks

8. Render is down: on the laptop, run `research/collect/session.sh start` and
   use http://localhost:8090/whatsapp and /talk.

### Real WhatsApp later

Until then the Twilio Sandbox (above, and docs/whatsapp-setup.md) carries
real messages for testing. When a registered business can be verified (Business Settings → Security
Center → Business verification), the same token, number and webhook start
delivering, with no code change.
