import type { ReactNode } from "react";
import { packInfo } from "../sample";
import { insightsOf, shop } from "../sample";
import { Chip, Page, Panel, Register, Tile } from "./Common";

/** What sample mode shows for pages that change the live engine: the same
 *  page, read-only, with sample values and a line saying where it is edited. */
function Banner() {
  return <div className="banner" role="note"><span><b>Preview.</b> Ye live engine pe edit hota hai. Yahan sirf dekh sakte ho, kuch save nahi hota.</span></div>;
}

export function SettingsPreview({ pack }: { pack: string }) {
  const rows: [string, ReactNode][] = [
    ["WhatsApp reminders", "On, a day before at 18:00 IST"], ["Deposit", "₹0 (off)"], ["Waitlist", "On"],
    ["Evening digest", "20:00 IST to the owner's WhatsApp"], ["Receptionist cost", "₹12,000 a month, 1,300 calls"],
    ["Calendar feed", "One link for Google, Apple or Outlook"], ["Users", "Owner and staff, by WhatsApp OTP"],
  ];
  return (
    <Page title="Settings" sub={`${packInfo(pack).business_name}: reminders, deposit, waitlist, digest, users.`}>
      <Banner />
      <Panel title="Booking settings" hint="sample values">
        <div className="body"><dl className="kv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div>
      </Panel>
    </Page>
  );
}

export function StudioPreview({ pack }: { pack: string }) {
  const p = packInfo(pack);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return (
    <Page title="Pack Studio" sub={`${p.business_name} · ${p.display_name}: what the agent knows, as one file.`}>
      <Banner />
      <Panel title="Services" hint={`${p.services.length} · prices and who does them`}>
        <Register head={<><th>Service</th><th className="right">Minutes</th><th className="right">Price</th><th>Staff</th><th>Callers also say</th></>}>
          {p.services.map((s) => (
            <tr key={s.name}><td><strong>{s.name}</strong></td><td className="num right">{s.duration_min}</td>
              <td className="num right">{s.price_inr ? `₹${s.price_inr.toLocaleString("en-IN")}` : "—"}</td>
              <td>{s.staff.join(", ")}</td><td className="muted">{s.aliases.slice(0, 5).join(", ")}</td></tr>
          ))}
        </Register>
      </Panel>
      <Panel title="Hours" hint="closed days say so to callers">
        <div className="body row">{DAYS.map((d, i) => {
          const h = p.hours[String(i)];
          return <Chip key={d} kind={h ? undefined : "muted"}>{d} {h ? `${h[0]}–${h[1]}` : "closed"}</Chip>;
        })}</div>
      </Panel>
    </Page>
  );
}

export function OpsPreview({ pack }: { pack: string }) {
  const s = shop(pack);
  const ins = insightsOf(s);
  const lat = s.calls.map((c) => c.latency_p50 ?? 0).filter((x) => x > 1).sort((a, b) => a - b);
  const q = (f: number) => (lat.length ? Math.round(lat[Math.min(lat.length - 1, Math.floor(f * lat.length))]!) : 0);
  return (
    <Page title="Ops" sub="Reply speed, speculation and counters, from the sample day.">
      <Banner />
      <div className="tiles">
        <Tile index={0} label="Calls today" value={s.calls.length} />
        <Tile index={1} label="p50 reply" value={q(.5)} suffix=" ms" mono />
        <Tile index={2} label="p90 reply" value={q(.9)} suffix=" ms" mono foot="target 1,500 ms" />
        <Tile index={3} label="Speculation hit" value={Math.round(ins.speculation.hit_rate * 100)} suffix="%" foot={`${ins.speculation.hits}/${ins.speculation.started}`} />
      </div>
    </Page>
  );
}
