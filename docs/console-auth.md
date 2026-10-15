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

1. Console kholo → number daalo → "Code bhejo". WhatsApp pe 6-digit code aata hai (5 minute, 5 koshish).
2. Code daalo → andar. Token 30 din chalta hai; "sign out" se khatam.
3. **Owner** sab kar sakta hai: packs edit, digest bhejna, users jodna. **Staff** sirf dekh sakta hai, aur sirf apne packs.

## Staff jodna

Abhi API se (console page agle version mein):

```bash
curl -X POST "$ENGINE/api/auth/users" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"98xxxxxxxx","role":"staff","packs":["dental_clinic"],"name":"Priya"}'
```

`packs: ["*"]` = sab packs. Hataana: `DELETE $ENGINE/api/auth/users/98xxxxxxxx`.

## Kya public rehta hai (login ke bina bhi)

Demo pages, caller ki sessions, WhatsApp webhook, public verifier ka export,
transparency log, recording aur study pages. Yani customer aur verifier ko
kabhi login nahi chahiye — sirf dukaan ke andar wale data ko.
