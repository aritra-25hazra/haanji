# Apna domain (jaise haanji.in)

Kharcha ≈ ₹500–800/saal (GoDaddy, Namecheap, ya Google Domains ka Indian
registrar). Do subdomain banao: `app.haanji.in` (console, Vercel) aur
`api.haanji.in` (engine, Render). Root `haanji.in` ko console pe bhejo.

## Render (engine)

1. Render dashboard → haanji-engine → Settings → Custom Domains → `api.haanji.in` add karo.
2. Render jo CNAME dikhaye wo registrar ke DNS mein daalo. TLS Render khud laga deta hai (10 min).
3. Environment mein: `HAANJI_PUBLIC_URL=https://api.haanji.in`, `HAANJI_CONSOLE_URL=https://app.haanji.in`,
   `HAANJI_CORS_ORIGIN_REGEX=https://(app\.)?haanji\.in|https://.*\.vercel\.app`.

## Vercel (console)

1. Vercel → project → Settings → Domains → `app.haanji.in` aur `haanji.in` add karo; DNS records jaise woh bataye.
2. `console/vercel.json` mein rewrites ka destination `https://api.haanji.in/...` kar do (abhi Render ka `.onrender.com` URL hai), phir `vercel --prod`.

## Baaki jagah jahan URL likha hai

- `render.yaml` → `HAANJI_CONSOLE_URL`
- `.github/workflows/transparency.yml` → `ENGINE`
- `.github/workflows/keep-awake.yml` → ping URL
- README ke badges aur "See it live" table
- Twilio webhook aur Meta WhatsApp webhook URL (dashboard mein)

Sab badalne ke baad `curl https://api.haanji.in/api/status` aur
`https://app.haanji.in` khol kar dekho; console ka "LIVE" chip hara hona chahiye.
