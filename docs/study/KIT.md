# Volunteer aur user-study kit (Steps B aur C)

Ye page aapke liye hai, jo sessions chalaoge. Ek insaan ke saath kul **15 minute**:

- **A. Awaaz record (5 min):** 20 chhote vaakya padhna. Isse pata chalta hai ki asli logon ki awaaz par recogniser kitni galtiyan karta hai aur Bhasha kitni sudhaarta hai (Step B).
- **B. User study (10 min):** HaanJi se 3 chhote kaam karwana, phir 10 sawaal (SUS) aur 2 line (Step C). Pura protocol: [protocol.md](protocol.md).

Kitne log: **8–10**. Hindi ya Bengali aur thodi English bolne wale, team ke bahar ke, jinhone kabhi clinic ya salon ko booking ke liye call kiya ho.

## Sab kuch isi laptop par rehta hai

Recordings aur answers sirf aapke laptop par rehte hain:

- awaaz `engine/var/recordings/` mein jaati hai;
- answers `engine/var/study.sqlite` mein;
- results `research/collect/data/volunteers/` mein.

Teeno gitignored hain. **Kabhi commit mat karna, kisi ko forward mat karna.** Report mein sirf jode hue numbers jaate hain (success rate, SUS, error rate). Participant ka naam kahin nahi likha jaata; sirf code (P01, P02, …).

## Session se pehle (ek baar)

1. Laptop par Chrome kholo. Mic chalna chahiye, aur kamra shaant ho.
2. Terminal mein, project folder mein:
   ```bash
   research/collect/session.sh start
   ```
   Ye local server chalata hai (`http://localhost:8090`). Session ke dauraan ise chalta rehne do.
3. (Optional) Doosre terminal mein `cd console && npm run dev` chalao, aur `http://localhost:5173/calls` par har call ka nateeja dekho. Ye runner's sheet bharne ke kaam aata hai.
4. [protocol.md](protocol.md) ki "Runner's sheet" print kar lo, ya har participant ke liye ek note bana lo.

## Har insaan ke saath (15 min)

1. Code do: P01, P02, … (naam mat likho).
2. **Awaaz:** `http://localhost:8090/record` kholo.
   - Page ka notice padhwao.
   - Pack chuno: Hindi bolne wale ke liye dental, Bengali ke liye clinic_kolkata.
   - 20 vaakya, normal awaaz mein, jaise likhe hain waise. Saaf bolne ki koshish nahi; galtiyan hi naapni hain.
3. **Study:** `http://localhost:8090/study` kholo.
   - Wahi code daalo.
   - 3 task cards ek-ek karke chalao. Aap chup raho, madad mat karo.
   - Har task ke baad wo "Ho gaya" ya "Nahi ho paya" dabayein.
4. 10 sawaal aur 2 line woh khud bharein.
5. Aakhri sawaal aap poochho aur unka jawab note karo: "Agar ye aapke dentist ka phone uthata, to aapko kis baat ki fikar hoti?"
6. Runner's sheet mein har task ka asli nateeja likho (console ki call list se).
7. Shukriya kaho ([invite-messages.md](invite-messages.md) mein message hai).

## Sab sessions ke baad

Server chalu rehte hue, doosre terminal mein:

```bash
research/collect/session.sh results
```

Ye do files banata hai, dono `research/collect/data/volunteers/` mein:

- `study_summary.md`: har task ka success, Wilson interval, time, SUS.
- `real_asr_volunteers.json`: asli awaaz par error rate, Bhasha ke bina aur saath.

In do files ko Claude ko do. Wo inhe REPORT §7 aur slides mein likhega, bina koi number badle. Runner's sheet ke notes bhi de do; failures ki list wahi se banti hai.

## 18 Dec tak ka plan

| kab | kya |
|---|---|
| is hafte | 10–12 logon ko invite bhejo (2–3 aakhri waqt pe mana karte hain) |
| agla hafta | sessions (ek din mein 4–5 aaram se) |
| 10 Dec tak | `session.sh results`, files Claude ko |
| 10–17 Dec | report aur slides mein asli numbers |

Agar kam log milein: 5 log bhi chalega. Report khud batayegi ki interval chauda hai, aur kitne logon par naapa.
