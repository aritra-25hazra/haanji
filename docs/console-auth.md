# Console login (owner aur staff)

Public demo mein console bina login ke khulta hai. Asli dukaan ke liye login
chalu karo — password nahi, WhatsApp pe ek baar ka code.

## Chalu karna (Render dashboard → Environment)

| key | value | kyun |
|---|---|---|
| `HAANJI_AUTH` | `on` | login zaroori ho jata hai |
| `HAANJI_OWNER_PHONE` | aapka WhatsApp number (10 digit) | pehla owner; shaam ka digest bhi isi pe |
| `HAANJI_AUTH_SECRET` | koi lambi random string (32+ chars) | tokens sign hote hain; badloge to sab logout |
| WhatsApp keys | (docs/whatsapp-setup.md) | code isi se jaata hai |

Bina WhatsApp ke test karna ho: `HAANJI_AUTH_DEV=1` — code response mein hi aa jata hai (sirf local/test ke liye).

## Kaise chalta hai

1. Console kholo → number daalo → "Code bhejo". WhatsApp pe 6-digit code aata hai (5 minute, 5 koshish). Ek number 15 minute mein 3 hi code maang sakta hai; 10 galat koshish ke baad 15 minute ka lock.
2. Code daalo → andar. Token 30 din chalta hai; "Sign out" is device se, Settings → "Sign out everywhere" har device se (saare tokens turant khatam). User hataane ya role badalne ka asar bhi turant hota hai, token ki expiry ka intezaar nahi.
3. **Owner** sab kar sakta hai: packs edit, settings, digest bhejna, users jodna, backup. **Staff** calendar chalaata hai (cancel / no-show / completed), customers dekhta hai, aur sirf apne packs; phone numbers staff ko masked dikhte hain.
4. `?pack=` ke bina koi request "sab packs" nahi maani jaati — jo pack tay na ho, wo request deny hoti hai.

Asli number pe code bhejne ke liye Meta ka **authentication template** chahiye
(`HAANJI_WA_TEMPLATE_OTP`), kyunki owner ne 24 ghante mein message na kiya ho to
free text deliver nahi hota; code na pahunche to API `503` deta hai, "sent" nahi.

## Staff jodna

Console → Settings → Users, ya API se:

```bash
curl -X POST "$ENGINE/api/auth/users" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"98xxxxxxxx","role":"staff","packs":["dental_clinic"],"name":"Priya"}'
```

`packs: ["*"]` = sab packs. Hataana: `DELETE $ENGINE/api/auth/users/98xxxxxxxx`.

## Kya public rehta hai (login ke bina bhi)

Demo pages, caller ki sessions, WhatsApp webhook, public verifier ka export,
transparency log, payment pages. Yani customer aur verifier ko kabhi login
nahi chahiye — sirf dukaan ke andar wale data ko. Login on hone pe WhatsApp
*simulator*, recording/study APIs, `/api/ops` aur `/metrics` bhi login ke
peeche aa jaate hain (ye demo/research surfaces hain, dukaan ke nahi).

## Email se code, password reset (Gmail)

Render mein ye 5 values daalo (sab `sync: false`, sirf dashboard mein):

1. Gmail account mein **2-Step Verification** on karo (myaccount.google.com → Security).
2. Wahi page pe **App passwords** → naam "HaanJi" → 16 akshar ka password milega.
3. Render → Environment:
   - `HAANJI_SMTP_HOST` = `smtp.gmail.com`
   - `HAANJI_SMTP_PORT` = `465`
   - `HAANJI_SMTP_USER` = aapka Gmail
   - `HAANJI_SMTP_PASSWORD` = App password (asli Gmail password kabhi nahi)
   - `HAANJI_MAIL_FROM` = `HaanJi <aapka@gmail.com>`

Iske baad login page pe **"Iske bajaye email pe code"** aur **"Password bhool gaye?"** dikhenge.

- Code 5 minute chalta hai, ek hi baar. 15 minute mein 3 se zyada code nahi.
- 10 galat code → 15 minute ka lock.
- Jawab hamesha same hota hai, chahe email ka account ho ya na ho, taaki koi
  account dhoondh na sake. Mail jawab ke baad jaati hai, to time se bhi pata nahi chalta.
- Reset ke baad har device se sign out ho jata hai, aur galat-password wala lock hat jata hai.
- `/api/status` → `mail.last_send` batata hai aakhri mail gayi ya nahi (email aadha chhupa hua, password kabhi nahi).

## 2-step login (authenticator app)

Settings → **Two-step sign-in** → "chalu karo":

1. QR ko Google Authenticator / Microsoft Authenticator / Authy se scan karo.
2. App ka 6 ankon ka code daalo → **Pakka karo**.
3. 8 recovery codes dikhenge, **sirf ek baar**. Save kar lo; phone kho jaye to har code ek baar chalega.

Uske baad har login (password, email code, WhatsApp code, Google) ke baad app ka code maanga jata hai.
Pehle step ke baad 5 minute ka ek-baar wala ticket milta hai; token sirf dusre step ke baad.
Ek code dobara nahi chalta. 10 galat code → 15 minute lock. Band karne ke liye abhi ka code (ya recovery code) chahiye.
App ka secret database mein encrypted rehta hai (`HAANJI_AUTH_SECRET` se bani key). Is wajah se
`HAANJI_AUTH_SECRET` kabhi mat badlo: badla to sabke 2-step secret khul nahi payenge aur 2-step dobara set karna padega.

**Phone aur recovery codes dono kho gaye?**
- Staff ke liye: owner Settings → Users mein unhe hatao aur dobara jodo. Isse unka 2-step band ho jata hai.
- Owner ke liye: Render → Environment mein `HAANJI_2FA_RESET` = apna email daalo. Restart ke baad 2-step band ho jayega.
  Sign in karke ye variable **turant hata do**, aur Settings se 2-step dobara chalu karo.
