import { Link, useNavigate } from "react-router-dom";
import PACKS from "../packs.json";
import { Icon } from "../components/Common";
import { t, useT } from "../i18n";
import { MEASURED, measuredOn, ms, pct } from "../results";
import { useApp } from "../state";

// "Dental clinic (Pune, Marathinglish)" and "Dental clinic" are one kind of shop.
const KINDS = [...new Set((PACKS as { packs: { display_name: string }[] }).packs.map((p) => p.display_name.replace(/\s*\(.*\)$/, "")))];

/** The console's front door for someone who has never seen HaanJi: what it
 *  does, the three measured ideas behind it, and two ways to try it. */
export default function Home() {
  useT();
  const { setSampleView, status } = useApp();
  const nav = useNavigate();
  const h = MEASURED.headline, led = MEASURED.ledger;
  const sales = status?.sales_whatsapp?.replace(/\D/g, "");
  const demo = () => { setSampleView(true); nav("/dashboard"); };
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
        <p className="home-lede">{t("HaanJi picks up your shop's phone and WhatsApp, books the appointment in your calendar, and keeps a signed receipt of what the caller agreed to.")}</p>
        <div className="row">
          <button className="btn btn-primary" onClick={demo}>{t("See the demo dashboard")} <Icon name="arrow" small /></button>
          <a className="btn btn-ghost" href="/engine/talk" target="_blank" rel="noopener noreferrer">{t("Talk to HaanJi")} <Icon name="external" small /></a>
          <Link className="btn btn-ghost" to="/how">{t("How it works")}</Link>
        </div>
        <p className="muted small">{t("Made for")} {KINDS.join(" · ")}</p>
      </section>

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
        <Link to="/how">{t("See every number")}</Link>
      </p>

      <section className="home-plans" aria-labelledby="plans-h">
        <h2 id="plans-h">{t("Plans")}</h2>
        <div className="plans">
          {[
            { name: t("Pilot"), text: t("One shop, set up together with you, to see it work on your own calls.") },
            { name: t("Shop"), text: t("Phone and WhatsApp, the calendar, reminders, and the owner's evening summary.") },
            { name: t("Chain"), text: t("Several branches in one dashboard, with sign-in for each person on the staff.") },
          ].map((p) => (
            <article key={p.name} className="plan">
              <h3>{p.name}</h3>
              <p>{p.text}</p>
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
    </div>
  );
}
