import type { ReactNode } from "react";
import { en, t, useT } from "../i18n";
import { packInfo } from "../sample";
import { insightsOf, shop } from "../sample";
import { Chip, Page, Panel, Register, Tile } from "./Common";

/** What sample mode shows for pages that change the live engine: the same
 *  page, read-only, with sample values and a line saying where it is edited. */
function Banner() {
  useT();
  return <div className="banner" role="note"><span><b>{t("Preview.")}</b> {t("This is edited on the live engine. Here you can only look; nothing is saved.")}</span></div>;
}

const SETTINGS_ROWS: [string, string][] = [
  [en("WhatsApp reminders"), en("On, a day before at 18:00 IST")], [en("Deposit"), en("₹0 (off)")], [en("Waitlist"), en("On")],
  [en("Evening digest"), en("20:00 IST to the owner's WhatsApp")], [en("Receptionist cost"), en("₹12,000 a month, 1,300 calls")],
  [en("Calendar feed"), en("One link for Google, Apple or Outlook")], [en("Users"), en("Owner and staff, by WhatsApp OTP")],
];

export function SettingsPreview({ pack }: { pack: string }) {
  useT();
  const rows: [string, ReactNode][] = SETTINGS_ROWS.map(([k, v]) => [t(k), t(v)]);
  return (
    <Page title="Settings" sub={t("{business}: reminders, deposit, waitlist, digest, users.", { business: packInfo(pack).business_name })}>
      <Banner />
      <Panel title="Booking settings" hint={t("sample values")}>
        <div className="body"><dl className="kv">{rows.map(([k, v]) => <div key={String(k)}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div>
      </Panel>
    </Page>
  );
}

const DAYS = [en("Mon"), en("Tue"), en("Wed"), en("Thu"), en("Fri"), en("Sat"), en("Sun")];

export function StudioPreview({ pack }: { pack: string }) {
  useT();
  const p = packInfo(pack);
  return (
    <Page title="Pack Studio" sub={t("{business} · {kind}: what the agent knows, as one file.", { business: p.business_name, kind: p.display_name })}>
      <Banner />
      <Panel title="Services" hint={t("{n} · prices and who does them", { n: p.services.length })}>
        <Register head={<><th>Service</th><th className="right">{t("Minutes")}</th><th className="right">{t("Price")}</th><th>Staff</th><th>{t("Callers also say")}</th></>}>
          {p.services.map((s) => (
            <tr key={s.name}><td><strong>{s.name}</strong></td><td className="num right">{s.duration_min}</td>
              <td className="num right">{s.price_inr ? `₹${s.price_inr.toLocaleString("en-IN")}` : "—"}</td>
              <td>{s.staff.join(", ")}</td><td className="muted">{s.aliases.slice(0, 5).join(", ")}</td></tr>
          ))}
        </Register>
      </Panel>
      <Panel title={t("Hours")} hint={t("on a closed day the agent tells callers so")}>
        <div className="body row">{DAYS.map((d, i) => {
          const h = p.hours[String(i)];
          return <Chip key={d} kind={h ? undefined : "muted"}>{t(d)} {h ? `${h[0]}–${h[1]}` : t("closed")}</Chip>;
        })}</div>
      </Panel>
    </Page>
  );
}

export function OpsPreview({ pack }: { pack: string }) {
  useT();
  const s = shop(pack);
  const ins = insightsOf(s);
  const lat = s.calls.map((c) => c.latency_p50 ?? 0).filter((x) => x > 1).sort((a, b) => a - b);
  const q = (f: number) => (lat.length ? Math.round(lat[Math.min(lat.length - 1, Math.floor(f * lat.length))]!) : 0);
  return (
    <Page title="Ops" sub={t("Reply speed, speculation and counters, from the sample day.")}>
      <Banner />
      <div className="tiles">
        <Tile index={0} label={t("Calls today")} value={s.calls.length} />
        <Tile index={1} label={t("p50 reply")} value={q(.5)} suffix=" ms" mono />
        <Tile index={2} label={t("p90 reply")} value={q(.9)} suffix=" ms" mono foot={t("target 1,500 ms")} />
        <Tile index={3} label="Speculation hit" value={Math.round(ins.speculation.hit_rate * 100)} suffix="%" foot={`${ins.speculation.hits}/${ins.speculation.started}`} />
      </div>
    </Page>
  );
}
