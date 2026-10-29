# Asli phone number jodna (Twilio + Deepgram + ElevenLabs)

Engine ke paas ab ek telephony bridge hai: caller ki awaaz Twilio se WebSocket
pe aati hai, Deepgram use Hinglish text banata hai (partials speculation ko
milte hain, finals policy ko), engine jawab deta hai, ElevenLabs use awaaz
banata hai aur wohi WebSocket wapas Twilio ko bhejta hai. Caller beech mein
bole to agent chup ho jaata hai (barge-in), bilkul browser demo jaisa.

Code: `engine/haanji/telephony/`. Bina keys ke bridge sirf tests mein chalta hai
(fake recogniser/synth ke saath); keys daalte hi asli.

## Kharcha (lagbhag, 2026)

| | free tier | uske baad |
|---|---|---|
| Twilio number + minutes | $15 trial credit; US number ~$1.15/mahina; inbound ~$0.0085/min | Indian number ke liye KYC + regulatory bundle (hafte lagte hain); shuru US number se karo |
| Deepgram (STT) | $200 credit | ~$0.0077/min (nova-2) |
| ElevenLabs (TTS) | 10k chars/mahina free | ~$5/mahina starter |

Ek 2-minute call ≈ ₹2–3. Yahi number README ke cost model mein hai.

## Steps

1. **Deepgram**: console.deepgram.com → API key banao → Render dashboard mein `HAANJI_DEEPGRAM_KEY`.
2. **ElevenLabs**: elevenlabs.io → Profile → API key → `HAANJI_ELEVENLABS_KEY`. Voices mein koi Hindi-capable voice chuno (multilingual v2 model Hindi bolta hai) → uska Voice ID → `HAANJI_ELEVENLABS_VOICE`.
3. **Twilio**: twilio.com → trial → ek number lo (Voice capable). Console → Phone Numbers → us number → Voice & Fax → "A call comes in" = **Webhook**, URL:
   ```
   https://haanji-engine.onrender.com/telephony/twilio/voice?pack=dental_clinic
   ```
   Method POST. Account → Auth Token copy → `HAANJI_TWILIO_AUTH_TOKEN` (isse engine har webhook ka signature check karta hai).
4. `HAANJI_PHONE_DISPLAY` = number jaise `+1 415 555 0100` (landing/console pe dikhane ke liye).
5. Render redeploy. `/api/status` mein `phone.configured: true` dikhna chahiye.
6. Trial mein sirf **verified** numbers se call aa sakti hai — Twilio console mein apna number verify karo, phir call karo. Agent uthayega: "Haanji, Smile Care Dental…"

## Agar kuch na chale

- Twilio ki call pe sirf "An application error has occurred" → webhook URL galat ya engine so raha hai (free Render 15 min baad sota hai; keep-awake action chalti hai par pehli call 30 s le sakti hai).
- Agent bolta hai par sunta nahi → Deepgram key galat; Render logs mein `deepgram` dekho.
- Sunta hai par bolta nahi → ElevenLabs key/voice galat.
- Barge-in nahi ho raha → normal hai agar Twilio ka audio buffer bada ho; engine `clear` bhejta hai, Twilio 1 s tak khaali karta hai.

## Exotel / Plivo (Indian numbers)

Bridge Twilio Media Streams ke protocol pe likha hai. Exotel ka "Voicebot
applet" aur Plivo ka "Audio Streams" bhi WebSocket pe μ-law bhejte hain; sirf
event ke naam alag hain. `haanji/telephony/twilio.py` ka `run()` wahi jagah hai
jahan unka adapter aayega — call ka baaki sab same rehta hai.

## 1.1: proxy, signature, ticket, audio

* Render ke peeche engine `X-Forwarded-*` headers trust karta hai (`RENDER`
  env se apne aap; kisi aur proxy pe `HAANJI_BEHIND_PROXY=1`), isliye Twilio
  ki `https://` signature sahi URL par check hoti hai.
* Public server pe `HAANJI_TWILIO_AUTH_TOKEN` zaroori hai; bina iske voice
  webhook `403` deta hai.
* Media WebSocket pe koi Twilio signature nahi hoti, isliye `/voice` ek
  one-time **ticket** TwiML `<Parameter>` mein deta hai jo stream shuru hote
  hi ek baar check hota hai (2 minute valid). Bina ticket ka stream band.
* Caller ka "haan" wala audio (agent ke aakhri line ke baad se) receipt mein
  SHA-256 ke roop mein jaata hai; `HAANJI_CONFIRMATION_AUDIO_DIR` set ho to
  clip bhi `<code>.ulaw` naam se rakhi jaati hai.
* Missed-call webhook (`/api/telephony/missed-call`) `HAANJI_MISSED_CALL_SECRET`
  ko `X-HaanJi-Secret` header mein maangta hai, aur asli WhatsApp number
  connected ho to outreach sach mein bhejta hai (pehle sirf store mein likhta tha).
