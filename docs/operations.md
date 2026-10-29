# Dukaan chalaana: reminders, deposit, waitlist, backup

Ye sab engine mein hai aur console ke **Settings** page se chalta hai (owner
login). Har cheez default pe sensible hai; keys sirf tab chahiye jab asli
WhatsApp / payment lagana ho.

## Reminders (no-show kam karne ka sabse sasta tareeka)

* Booking se ek din pehle, `reminder_hour_ist` (default shaam 6) par caller ko
  WhatsApp jaata hai: kya, kab, kiske saath, confirmation code.
* Caller **1** likhe to confirm; **2** likhe to booking cancel — ledger ke
  through, jahan reminder hi "sawaal" hai aur reply hi "proof". Ek reminder
  ka jawab ek baar hi maana jaata hai.
* Same-day mode: `reminder_day_before: false` → booking se do ghante pehle.
* Meta 24 ghante ki window ke bahar free text nahi bhejta. Asli number pe
  reminders ke liye ek **approved template** chahiye; uska naam
  `HAANJI_WA_TEMPLATE_REMINDER` mein daalo (body params: service, date time).
  Template na ho to engine text try karta hai aur delivery result log karta hai.

## Deposit (UPI / card link har booking ke saath)

* Settings → `deposit_inr` (jaise 300). Har nayi booking ki confirmation ke
  saath payment link jaata hai (WhatsApp reply mein, web caller ko WhatsApp
  pe agar number connected hai).
* **Keys ke bina:** link is server ka `/pay/<id>` page hai — demo ke liye ek
  click mein "paid". **Razorpay ke saath:** `HAANJI_RAZORPAY_KEY_ID`,
  `HAANJI_RAZORPAY_KEY_SECRET`, aur webhook ke liye
  `HAANJI_RAZORPAY_WEBHOOK_SECRET`; Razorpay dashboard mein webhook URL
  `https://<engine>/payments/razorpay/webhook`, event `payment_link.paid`.
* Paid hone pe booking `paid` ho jaati hai (calendar mein chip) aur ledger
  mein `payment_received` receipt banta hai — paisa bhi chain mein dikhta hai.

## Waitlist (khaali hua slot pehle usko jo intezaar kar raha tha)

* Caller ne jo din maanga wo bhara ho aur wo naam-number de de, to lead ke
  saath us din ki waitlist mein bhi aa jaata hai (agent khud bolta hai "slot
  khaali hua to sabse pehle aapko WhatsApp karenge").
* Us din koi booking cancel ho — caller se, reminder ke "2" se, ya console se —
  to pehle waiting wale ko WhatsApp jaata hai slot ke saath; wo "haan" likhe to
  wahi read-back, wahi receipt.
* Console → Calendar → Waitlist panel mein entries dikhti hain; hataa bhi
  sakte ho. `waitlist_on: false` se band.

## Calendar, customers, settings

* **Calendar:** din/hafte ka view, har booking pe Cancel / No-show / Completed.
  Har action ledger mein `staff_cancel` / `staff_update` ke roop mein seal hota
  hai, kisne kiya uske naam ke saath.
* **Customers:** har number ek row — naam, visits, last service, no-shows;
  owner ke liye privacy record aur erase yahin se.
* **Settings:** reminders, deposit, waitlist, digest ka time; staff users
  (add/remove, role, packs); WhatsApp/phone/Google status; "Sign out
  everywhere" (saare tokens turant khatam).

## Backup (Render ki disk redeploy pe saaf ho jaati hai)

* **Download:** console → Settings → Backup, ya `GET /api/admin/backup`
  (owner). Ek `tar.gz` jisme har SQLite consistent copy ke saath (online
  backup API, file copy nahi), keys aur VAPID bhi.
* **Nightly S3:** `HAANJI_BACKUP_S3_BUCKET` (+ `HAANJI_BACKUP_S3_PREFIX`,
  R2/MinIO ke liye `HAANJI_BACKUP_S3_ENDPOINT`, credentials `AWS_*`). Roz
  digest ke waqt upload. `pip install "haanji-engine[backup]"` (boto3).
* **Restore on boot:** `HAANJI_RESTORE_FROM=s3` (bucket ka sabse naya) ya
  koi `https://` URL. Sirf **khaali** data directory mein restore hota hai —
  chalti dukaan ke upar kabhi nahi.
* CLI: `haanji backup --out file.tar.gz [--s3]`, `haanji restore file.tar.gz
  [--force]`.

## Security knobs (asli dukaan ke liye)

| key | kya |
|---|---|
| `HAANJI_AUTH=on` + `HAANJI_OWNER_PHONE` | console login (docs/console-auth.md) |
| `HAANJI_LEDGER_KEY_SECRET` | ledger ki signing keys disk pe encrypted |
| `HAANJI_METRICS_TOKEN` | `/metrics` sirf Prometheus ke bearer token se |
| `HAANJI_MISSED_CALL_SECRET` | missed-call webhook ka `X-HaanJi-Secret` |
| `HAANJI_WA_APP_SECRET`, `HAANJI_TWILIO_AUTH_TOKEN` | public server pe webhook signatures zaroori hain; bina inke engine unsigned deliveries reject karta hai |
| `HAANJI_CONFIRMATION_AUDIO_DIR` | phone pe caller ka "haan" wala audio clip receipt code ke naam se rakho; receipt mein uska SHA-256 hai |
| `HAANJI_MAX_CONCURRENT_CALLS` (25) | isse zyada live calls → 429 |
| `HAANJI_DEMO=1` | demo customer ("Vijay ji") seed hota hai; auth on hone pe default band |
