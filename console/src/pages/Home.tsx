import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Icon } from "../components/Common";
import { en, t, useT } from "../i18n";
import { MEASURED, measuredOn, ms, pct } from "../results";
import { useApp } from "../state";

// HaanJi is built for two kinds of business: clinics and coaching institutes.
const KINDS = [
  { icon: "tooth", name: en("Clinics"), text: en("Dental, general surgery, general physician, paediatrics, orthopaedics and gynaecology: the caller is booked with the right doctor, and emergencies go straight to a person.") },
  { icon: "bell", name: en("A token queue at reception"), text: en("Booked patients check in and walk-ins get a token; reception calls the next one, a waiting-room screen shows who is being seen, and a caller can ask how long the wait is.") },
  { icon: "book", name: en("Coaching institutes"), text: en("Class 10 and 11–12 boards (CBSE, ICSE, IB), JEE and NEET: demo classes, counselling and scholarship tests, and never a promised rank.") },
];
const FAQ = [
  { q: en("Is it really AI?"), a: en("Yes, in the plain sense: it listens with speech recognition, works out what the caller wants and answers in their language. What to ask and what to book is decided by HaanJi's own rules for each kind of shop, which is why every booking can be checked; a hosted model (Google Gemini) can be switched on. It tells every caller that it is an AI.") },
  { q: en("Does it speak Hindi?"), a: en("Yes, Hinglish, the way people mix Hindi and English on the phone. The engine has also been tested with Bengali, Marathi, Tamil, Telugu, Gujarati and Punjabi mixed with English.") },
  { q: en("How does the token queue work?"), a: en("When a booked patient arrives, reception checks them in and they get a token such as GP-07; a walk-in gets one at the desk. Reception presses Next patient for each doctor, the waiting-room screen shows the token being seen (never a name), and a patient can call or message to ask how many are ahead.") },
  { q: en("What if it gets it wrong?"), a: en("It reads every booking back (service, day, time and the last digits of the number) and books only after the caller says yes. If it cannot finish, it takes a callback note, and the call shows up under 'Needs a callback'. Emergencies and complaints go to your staff.") },
  { q: en("Is my data safe?"), a: en("Customers' names and numbers in each receipt are encrypted with a key per customer. A customer can download their data or ask for it to be erased on the My data page, and call records are deleted after 180 days by default. The public demo shows made-up data only.") },
];

/** The console's front door for someone who has never seen HaanJi: what it
 *  does, the three measured ideas behind it, and two ways to try it. */
export default function Home() {
  useT();
  const { setSampleView, status } = useApp();
  const nav = useNavigate();
  const h = MEASURED.headline, led = MEASURED.ledger;
  const sales = status?.sales_whatsapp?.replace(/\D/g, "");
  const demo = () => { setSampleView(true); nav("/dashboard"); };
  useEffect(() => { document.title = t("HaanJi — AI receptionist for clinics and coaching institutes"); });
  const ideas = [
    { name: "Bhasha", title: t("Hears shop words right"),
      num: `${pct(h.entity_error_rate_without_bhasha!)} → ${pct(h.entity_error_rate_with_bhasha!, 2)}`,
      text: t("misheard names, services and times when the speech recogniser gets {noise} of words wrong; {harm} corrections made a word worse.", { noise: pct(h.noise_rate!, 0), harm: h.harmful_corrections_transcript! }) },
    { name: t("Speculative turns"), title: t("Answers sooner"),
      num: `${ms(h.read_turn_p50_without_speculation!)} → ${ms(h.read_turn_p50_with_speculation!)}`,
      text: t("median reply on questions like \"is 5 pm free?\": the lookup starts while the caller is still talking, and is used only if the question matches exactly.") },
    { name: "Pramaan", title: t("Proves every booking"),
      num: `${led.mutations_detected} / ${led.mutations_attempted}`,
      text: t("edited receipts caught. Nothing is booked before the caller says yes to a read-back; {u} bookings were written without that yes.", { u: led.unconfirmed_writes_accepted }) },
  ];
  return (
    <div className="home">
      <section className="home-hero">
        <h1>{t("A receptionist that answers every call, in Hinglish.")}</h1>
        <p className="home-lede">{t("For clinics and coaching institutes: HaanJi picks up the phone and WhatsApp, books the right doctor or class, runs the token queue at reception, and keeps a signed receipt of what the caller agreed to.")}</p>
        <div className="row">
          <button className="btn btn-primary" onClick={demo}>{t("See the demo dashboard")} <Icon name="arrow" small /></button>
          <a className="btn btn-ghost" href="/engine/talk" target="_blank" rel="noopener noreferrer">{t("Talk to HaanJi")} <Icon name="external" small /></a>
          <Link className="btn btn-ghost" to="/how">{t("How it works")}</Link>
        </div>
      </section>

      <figure className="home-shot">
        <img src="/shot-dashboard.webp" width={1448} height={924} loading="lazy"
             alt={t("The owner's Today screen: calls, bookings, who needs a callback and what the engine noticed.")} />
        <figcaption className="muted small">{t("The owner's Today screen (sample data).")}</figcaption>
      </figure>

      <section className="home-ideas" aria-label={t("The three ideas")}>
        {ideas.map((i) => (
          <article key={i.name} className="idea">
            <p className="idea-name">{i.name}</p>
            <h2>{i.title}</h2>
            <p className="idea-num mono">{i.num}</p>
            <p>{i.text}</p>
          </article>
        ))}
      </section>
      <p className="muted small home-note">
        {t("Measured on {date} by the project's benchmark: {scenarios} scripted calls across {packs} shops, {reps} runs each, with speech-recognition errors added on purpose. These are simulated calls, not live customers.", { date: measuredOn(), scenarios: MEASURED.scenarios, packs: MEASURED.packs, reps: MEASURED.reps })}{" "}
        {t("On errors learned from real speech recognisers the reduction is smaller, 28–33%.")}{" "}
        <Link to="/how">{t("See every number")}</Link>
      </p>

      <section className="home-who" aria-labelledby="who-h">
        <h2 id="who-h">{t("Who it's for")}</h2>
        <div className="who-grid">
          {KINDS.map((k) => (
            <article key={k.name} className="who">
              <span className="who-icon"><Icon name={k.icon} /></span>
              <h3>{t(k.name)}</h3>
              <p>{t(k.text)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-plans" id="plans" aria-labelledby="plans-h">
        <h2 id="plans-h">{t("Plans")}</h2>
        <div className="plans">
          {[
            { name: t("Pilot"), text: t("One clinic or institute, set up together with you, to see it work on your own calls."),
              points: [en("Your services, prices, hours and staff set up for you"), en("Calls in the browser and the WhatsApp simulator"), en("The owner's console and signed receipts")] },
            { name: t("Clinic"), text: t("Phone and WhatsApp, the calendar, the token queue, reminders, and the owner's evening summary."),
              points: [en("Bookings straight into each doctor's calendar"), en("A token queue with a waiting-room screen"), en("WhatsApp reminders the day before"), en("Callback list for calls it could not finish")] },
            { name: t("Group"), text: t("Several branches in one dashboard, with sign-in for each person on the staff."),
              points: [en("One console for every branch"), en("Owner and staff sign-in, each device listed"), en("An activity log of every change"), en("Customers' data requests handled in Settings")] },
          ].map((p) => (
            <article key={p.name} className="plan">
              <h3>{p.name}</h3>
              <p>{p.text}</p>
              <ul className="plan-points">{p.points.map((x) => <li key={x}><Icon name="check" small />{t(x)}</li>)}</ul>
              <p className="muted small">{t("Price on request")}</p>
            </article>
          ))}
        </div>
        <div className="row">
          {sales
            ? <a className="btn btn-primary" href={`https://wa.me/${sales}?text=${encodeURIComponent(t("Hi, I would like a HaanJi demo for my shop."))}`} target="_blank" rel="noopener noreferrer">{t("Ask for a demo on WhatsApp")} <Icon name="external" small /></a>
            : <button className="btn btn-primary" onClick={demo}>{t("See the demo dashboard")} <Icon name="arrow" small /></button>}
        </div>
      </section>

      <section className="home-faq" aria-labelledby="faq-h">
        <h2 id="faq-h">{t("Questions")}</h2>
        {FAQ.map((f) => (
          <details key={f.q} className="faq">
            <summary>{t(f.q)}</summary>
            <p>{t(f.a)}</p>
          </details>
        ))}
      </section>
    </div>
  );
}
