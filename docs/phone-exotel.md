# Exotel se asli phone call: runbook (demo se pehle, ~11–12 Dec)

Code taiyaar hai aur tests mein chalta hai (`tests/test_telephony_exotel.py`).
Ye page sirf wo steps hain jo **aapko** karne hain, kram se. Koi bhi paid step
aaye to ruk jao aur pehle kharcha dekh lo.

## Kya-kya chahiye

| Cheez | Kahan | Kaam |
|---|---|---|
| Exotel trial account | exotel.com | Indian number, call ko engine tak bhejna |
| Deepgram API key | console.deepgram.com | caller ki awaaz → Hinglish text |
| ElevenLabs API key + voice | elevenlabs.io | jawab → awaaz |
| Ek lamba random secret | khud banao | Exotel ke stream URL ki chaabi |

Kharcha: Exotel trial, Deepgram ka free credit aur ElevenLabs ka free tier
sign-up ke waqt jo dikhaye wahi maano. Yahan koi rate nahi likha, kyunki ye
badalte rehte hain. Card maange to ruk jao aur pehle poochho.

## Steps

1. **Exotel trial** lo. KYC maange to wahi karo jo Exotel bole.
2. Exotel support se likh ke poochho: *"Please enable AgentStream (Voicebot
   applet, bidirectional) on my trial account."* Trial pe ye by default band
   ho sakta hai. Jab tak wo haan na bolein, aage ka step kaam nahi karega.
3. **Secret banao** (laptop pe):
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(24))"
   ```
4. **Render → haanji-engine → Environment** mein daalo (sab sirf dashboard mein):
   - `HAANJI_EXOTEL_STREAM_KEY` = step 3 ka secret
   - `HAANJI_DEEPGRAM_KEY` = Deepgram key
   - `HAANJI_ELEVENLABS_KEY` = ElevenLabs key
   - `HAANJI_ELEVENLABS_VOICE` = ek Hindi bolne wali voice ka Voice ID
   - `HAANJI_PHONE_DISPLAY` = Exotel number, jaise `+91 80 4XXX XXXX` (sirf dikhane ke liye)

   Optional: `HAANJI_STT_LANGUAGE` (default `hi-Latn`), `HAANJI_ELEVENLABS_MODEL`.
5. Render redeploy hone do. `https://haanji-engine.onrender.com/api/status` kholo:
   `phone.configured` = `true` hona chahiye.
6. **Exotel App Bazaar → naya flow:**
   1. **Voicebot** applet, URL:
      ```
      wss://haanji-engine.onrender.com/telephony/exotel/stream?pack=smile_care_clinic&key=<step 3 ka secret>
      ```
      Bidirectional chuno.
   2. Uske baad **Hangup** applet.
   3. Flow ko apne Exotel number se jodo.
7. **Test call** (neeche checklist).

Demo server pe call apne aap "Smile Care Clinic (Demo)" mein jaati hai, jaise
`/talk` aur `/whatsapp` ke visitors. Coaching ke liye `pack=pragati_classes`.

## Test-call checklist

Call se 2 minute pehle `/api/status` kholo, taaki free Render jaag jaye.

- [ ] Phone uthte hi greeting aati hai ("Namaste, Smile Care Clinic…").
- [ ] "kal subah dant dikhana hai" bolo: slot offer hote hain.
- [ ] Slot chuno, naam batao, "haan" bolo: booking code bola jata hai.
- [ ] Console → Calls mein call `PHONE` channel ke saath dikhti hai.
- [ ] Agent ke bolte waqt beech mein bolo: agent chup ho jata hai (barge-in).
- [ ] Call kaato: console mein call band dikhti hai.

## Kuch nahi chala?

| Kya hua | Kya dekho |
|---|---|
| Call turant kat gayi | Render Logs mein `exotel stream without the right key was refused`: URL ki `key` aur `HAANJI_EXOTEL_STREAM_KEY` match nahi. |
| Ghanti bajti hai, koi awaaz nahi | AgentStream enable nahi hua (step 2), ya engine so raha tha (dobara call karo). |
| Greeting aati hai, sunta nahi | Deepgram key galat; Logs mein `deepgram`. |
| Sunta hai, bolta nahi | ElevenLabs key ya Voice ID galat. |
| `phone.configured: false` | Teeno keys (Deepgram, ElevenLabs key, Voice ID) daali hain? |

Security: stream URL ki `key` server ke access log mein `key=…` ban kar
chhupti hai. Phir bhi URL kisi ko mat bhejo; leak ho to naya secret banao aur
dono jagah badlo.

Protocol: https://developer.exotel.com/docs/agentstream/stream-voicebot-applet
Bina Exotel ke demo: `/talk` (browser mein wahi engine).
