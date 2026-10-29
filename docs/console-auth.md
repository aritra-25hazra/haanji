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
