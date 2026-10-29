/**
 * A fetch that plays the engine. Routes are "METHOD path" (GET when the method
 * is left out) relative to /engine/, with `*` matching one path segment. A
 * handler returns the JSON body, a `fail(...)` for an error response, throws
 * for a network failure, or never resolves. Every call is recorded.
 */
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { today } from "../dates";
import { AppProvider } from "../state";
import type { Booking, Settings, Status, User } from "../types";

export const STATUS_OPEN: Status = {
  name: "test engine", version: "1.1.0", default_pack: "dental_clinic", packs: ["dental_clinic", "salon_spa"],
  auth: { enabled: false }, whatsapp: { configured: false, number: null }, phone: { configured: false, number: null },
  google: { configured: false, connected: [] },
};
export const STATUS_AUTH: Status = { ...STATUS_OPEN, auth: { enabled: true } };
export const OWNER: User = { phone: "9876543210", role: "owner", packs: ["*"], name: "Asha" };
export const STAFF: User = { phone: "9811111111", role: "staff", packs: ["dental_clinic"], name: "Ravi" };
export const SETTINGS: Settings = {
  reminders_on: true, reminder_hour_ist: 18, reminder_day_before: true, deposit_inr: 0, waitlist_on: true, digest_hour_ist: 20, language_script: "latin",
};

export function booking(over: Partial<Booking> = {}): Booking {
  return {
    booking_id: "b1", service: "root canal", staff: "Dr Sheikh", date: today(), time: "09:30", duration_min: 60,
    customer_name: "Vijay Sharma", phone: "9876543210", status: "CONFIRMED", receipt_code: "2504-7863",
    created_at: "2026-10-29T08:00:00", paid: false, deposit_inr: 500, payment_link: null, reminder_sent_at: null, ...over,
  };
}

export interface Ctx { method: string; path: string; url: URL; body: unknown }
export type Handler = (ctx: Ctx) => unknown;
export interface Call { method: string; path: string; query: URLSearchParams; body: unknown }

class Fail {
  constructor(public status: number, public body: string, public contentType: string) {}
}
export const fail = (status: number, body: unknown, contentType = "application/json") =>
  new Fail(status, typeof body === "string" ? body : JSON.stringify(body), contentType);
/** The engine is unreachable: fetch itself rejects. */
export const down = (): never => { throw new TypeError("fetch failed"); };
/** The engine never answers. */
export const never = () => new Promise<never>(() => undefined);

const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status, headers: { "content-type": "application/json" } });

export function mockEngine(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const compiled = Object.entries(routes).map(([key, handler]) => {
    const sp = key.indexOf(" ");
    const method = sp > 0 ? key.slice(0, sp) : "GET";
    const pattern = sp > 0 ? key.slice(sp + 1) : key;
    const re = new RegExp("^" + pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]+") + "$");
    return { method, re, handler };
  });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://console.test");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/engine\//, "");
    let body: unknown;
    if (typeof init?.body === "string") { try { body = JSON.parse(init.body); } catch { body = init.body; } }
    calls.push({ method, path, query: url.searchParams, body });
    const match = compiled.find((c) => c.method === method && c.re.test(path));
    if (!match) return json({ detail: `no mock for ${method} ${path}` }, 404);
    const r = await match.handler({ method, path, url, body });
    if (r instanceof Fail) return new Response(r.body, { status: r.status, headers: { "content-type": r.contentType } });
    return json(r);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetch: fetchMock };
}

/** The whole console at a route, exactly as main.tsx mounts it (minus StrictMode). */
export function renderApp(path = "/calls") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProvider>
        <App />
      </AppProvider>
    </MemoryRouter>,
  );
}
