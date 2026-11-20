# Asli WhatsApp number jodna — step by step

Engine mein Meta WhatsApp Cloud API ka adapter pehle se hai. Aapko sirf Meta ki
taraf ek app banani hai aur 4 values Render mein daalni hain. Free hai, ~15 minute.

Jab ho jayega: koi bhi aapke test number pe WhatsApp message karega, HaanJi
jawab dega, booking karega, receipt banayega — aur console ke *Calls* mein
`whatsapp` channel ke saath dikhega.

## Jab tak Meta business verify nahi karta: Twilio Sandbox (free, ~10 min)

Meta ka account business verification tak band hai (131031). Tab tak asli
WhatsApp **Twilio Sandbox** se chal sakta hai. Code pehle se ready hai; Meta set
ho jayega to engine apne aap Meta use karega.

1. twilio.com pe free account banao (email aur phone verify).
2. Console mein: **Messaging → Try it out → Send a WhatsApp message**.
   Wahan Sandbox ka number (`+1 415 523 8886`) aur **join phrase** dikhega,
   jaise `join able-tiger`.
3. **Sandbox settings** mein "When a message comes in" mein ye daalo, method **POST**:
   `https://haanji-engine.onrender.com/wa/twilio`
   Save karo.
4. Twilio console ke home pe **Account SID** aur **Auth Token** milenge.
5. Render → haanji-engine → **Environment** mein 4 values daalo:
   - `HAANJI_TWILIO_ACCOUNT_SID` = Account SID (AC… se shuru)
   - `HAANJI_TWILIO_AUTH_TOKEN` = Auth Token
   - `HAANJI_TWILIO_WA_FROM` = `whatsapp:+14155238886`
   - `HAANJI_TWILIO_WA_JOIN` = jo join phrase dikha, jaise `join able-tiger`
   Save → engine restart hoga.
6. Test: apne phone se `+1 415 523 8886` pe WhatsApp mein join phrase bhejo,
   phir "Namaste" likho. HaanJi jawab dega.
7. `https://haanji-engine.onrender.com/api/status` mein `whatsapp.provider`
   `twilio` dikhna chahiye. `/whatsapp` page pe join ka button aur QR aa jayega.

Sandbox ki limits (Twilio ke docs, twilio.com/docs/whatsapp/sandbox):
- Sirf wahi number message paa sakte hain jinhone join phrase bheja ho (error 63015).
- Join karne ke **3 din baad** session khatam: join phrase dobara bhejna hoga.
- Free-form jawab sirf **aakhri message ke 24 ghante** ke andar. Login code ya
  reminder us window ke bahar nahi pahunchega; `/api/status` mein
  `whatsapp.last_send.delivery` "failed" dikhayega.
- Sandbox ek message har 3 second se zyada tez nahi bhejta.
- Ye sirf testing ke liye hai. Twilio trial credit message bhejne par use hota
  hai; rate Twilio ke pricing page pe dekho.

Demo server pe Sandbox se aane wale message "(Demo)" shop mein jaate hain,
bilkul simulator ki tarah, taaki asli clinic ka calendar saaf rahe.

## Pehle ye samajh lo (2 min)

- Meta ka **test number** free hai lekin sirf **5 phone numbers** ko message
  kar sakta hai — jo aap khud register karoge (aapka, dosto ke). Demo ke liye
  kaafi hai. Asli number ke liye business verification chahiye (baad mein).
- **Temporary token** 24 ghante chalta hai. Demo ke din naya le lena, ya neeche
  "permanent token" wala section karo.
- Engine sirf **24 ghante ke andar** free-form reply kar sakta hai jab user ne
  pehle message kiya ho (Meta ka rule). Hamare flow mein user hi pehle likhta
  hai, to theek hai.

## Part 1 — Meta app (10 min)

1. https://developers.facebook.com → **Get started** → Facebook account se login
   (nahi hai to ek bana lo).
2. Upar **My Apps** → **Create App** → use case mein **Other** → app type
   **Business** → naam `HaanJi` → **Create app**.
3. App dashboard pe **Add product** → **WhatsApp** → **Set up**. Business
   portfolio poochega to naya bana lo (koi bhi naam).
4. Left mein **WhatsApp → API Setup** kholo. Is page pe teen cheezein milengi —
   ek jagah note kar lo:
   - **Phone number ID** (ek lamba number) → ye `HAANJI_WA_PHONE_ID` hai
   - **Temporary access token** (`EAAG…` se shuru) → ye `HAANJI_WA_TOKEN` hai
   - **Test number** (`+1 555 …`) → isi pe log message karenge
5. Usi page pe **To** wale dropdown mein **Manage phone number list** → apna
   WhatsApp number add karo (+91 ke saath) → WhatsApp pe OTP aayega → verify.
   Dosto ke number bhi yahin (max 5).
6. Left mein **App settings → Basic** → **App secret** → **Show** → copy →
   ye `HAANJI_WA_APP_SECRET` hai. (Ye hi engine ko batata hai ki message sach
   mein Meta se aaya hai, kisi aur ne nahi bheja.)
7. Ek **verify token** khud soch lo — koi bhi random shabd, jaise
   `haanji-verify-2026`. Ye `HAANJI_WA_VERIFY_TOKEN` hai; abhi likh lo, do
   jagah daalna hai.

## Part 2 — Render mein values (3 min)

1. https://dashboard.render.com → **haanji-engine** → left mein **Environment**.
2. Ye variables bharo (naam bilkul same):

   | Naam | Value |
   |---|---|
   | `HAANJI_WA_TOKEN` | temporary access token (Part 1, step 4) |
   | `HAANJI_WA_PHONE_ID` | phone number ID (step 4) |
   | `HAANJI_WA_APP_SECRET` | app secret (step 6) |
   | `HAANJI_WA_VERIFY_TOKEN` | aapka verify token (step 7) |
   | `HAANJI_WA_DISPLAY_NUMBER` | test number jaise dikhana ho, e.g. `+1 555 012 3456` (optional) |
   | `HAANJI_WA_PACK` | `dental_clinic` (ya jo pack chahiye) |

3. **Save changes** → Render engine ko restart karega (~1 min). Phir check:
   https://haanji-engine.onrender.com/api/status mein `"whatsapp": {"configured": true, …}` dikhna chahiye.

## Part 3 — Webhook jodna (3 min)

1. Meta app dashboard → **WhatsApp → Configuration**.
2. **Webhook** → **Edit**:
   - **Callback URL:** `https://haanji-engine.onrender.com/wa/webhook`
   - **Verify token:** wahi jo aapne Render mein `HAANJI_WA_VERIFY_TOKEN` mein daala
   - **Verify and save**. (Agar "could not validate" aaye → Render ne restart
     poora nahi kiya, 1 min baad phir try karo; ya token mein typo.)
3. Usi page pe **Webhook fields** → **Manage** → `messages` ke saamne
   **Subscribe** → **Done**.

## Part 4 — Test (1 min)

Apne phone se test number pe WhatsApp pe likho: `hi`

HaanJi greeting bhejega. Phir `mujhe root canal karwana hai` → aage booking
tak le jao. Console (https://haanji-kappa.vercel.app) → **Calls** mein ye call
`whatsapp` channel ke saath dikhegi; **Pramaan** mein receipt.

## Kuch nahi hua? (troubleshooting)

| Dikkat | Wajah | Kya karo |
|---|---|---|
| Webhook verify fail | verify token alag hai, ya engine abhi restart ho raha hai | dono jagah token same karo; 1 min baad retry |
| Message bheja, jawab nahi | token expire (24 h) | Meta API Setup se naya temporary token → Render mein update |
| Jawab nahi, token theek hai | aapka number recipient list mein nahi | Part 1 step 5 |
| Render logs mein `403` | app secret galat | Part 1 step 6 dobara, Render mein paste |
| Engine so gaya tha | free plan | keep-awake chal raha hai; pehla message 20–30 s le sakta hai |

Render logs: dashboard → haanji-engine → **Logs**. Har aane wala message aur
bheja gaya reply wahan dikhta hai.

## Permanent token (jab demo ke din roz naya token nahi lena ho)

1. https://business.facebook.com → **Settings → Business settings → Users →
   System users** → **Add** → naam `haanji-bot`, role **Admin** → Create.
2. Us user pe **Add assets** → **Apps** → `HaanJi` → **Manage app** → Save.
3. **Generate new token** → app `HaanJi` → expiry **Never** → permissions mein
   `whatsapp_business_messaging` aur `whatsapp_business_management` tick →
   Generate → copy.
4. Render mein `HAANJI_WA_TOKEN` is token se badal do. Ab expire nahi hoga.

## Asli (apna) number

Test number ke bajaye apna business number jodne ke liye Meta Business
verification chahiye (GST/udyam jaisa document) aur ek number jo pehle se
WhatsApp pe na ho. Ye college demo ke liye zaroori nahi — test number +
5 recipients kaafi hai.

## Templates (24 ghante ki window ke bahar)

Meta free text sirf customer ke aakhri message ke 24 ghante tak deliver karta
hai. Jo messages dukaan khud shuru karti hai — login code, reminder, receipt
link, digest, missed-call outreach, waitlist offer — unke liye Meta Business
Manager mein **template** banao (approval 1–2 din), phir naam env mein:

| key | template ka kaam | body params |
|---|---|---|
| `HAANJI_WA_TEMPLATE_OTP` | authentication template | `{{1}}` = code |
| `HAANJI_WA_TEMPLATE_REMINDER` | utility: "aapki {{1}} booking {{2}} ko hai; 1 = haan, 2 = cancel" | service, date time |
| `HAANJI_WA_TEMPLATE_RECEIPT` | utility: receipt link | code |
| `HAANJI_WA_TEMPLATE_OUTREACH` | utility: missed call / waitlist | business name |
| `HAANJI_WA_TEMPLATE_DIGEST` | utility: owner ka digest | — |

`HAANJI_WA_TEMPLATE_LANG` (default `en`). Template na ho to engine text
bhejta hai aur `delivered: false` log karta hai — "sent" kabhi jhooth nahi.

**Security:** public server (`RENDER_EXTERNAL_URL`/`HAANJI_PUBLIC_URL` set) pe
`HAANJI_WA_APP_SECRET` zaroori hai; bina iske webhook unsigned deliveries
reject karta hai. `HAANJI_WA_VERIFY_TOKEN` bhi set karo (default sirf local
ke liye hai).
