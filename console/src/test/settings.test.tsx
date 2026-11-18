import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OWNER, SETTINGS, STATUS_AUTH, mockEngine, renderApp } from "./mock";

const ownerRoutes = {
  "api/status": () => STATUS_AUTH,
  "api/auth/me": () => ({ enabled: true, user: OWNER }),
  "api/settings": () => SETTINGS,
  "api/google/status": () => ({ configured: false, connected: false, connected_at: null, redirect_uri: "" }),
  "api/calendar/feed-url": () => ({ pack: "dental_clinic", url: "https://engine.test/calendar/dental_clinic.ics", webcal: "webcal://engine.test/calendar/dental_clinic.ics" }),
  "api/digest": () => ({ pack: "dental_clinic", text: "Aaj 3 bookings.", to: null, whatsapp_configured: false, hour_ist: 20 }),
  "api/auth/users": () => ({ users: [OWNER] }),
};

describe("settings", () => {
  it("saves only the changed keys with PUT /api/settings", async () => {
    localStorage.setItem("haanji.token", "tok");
    const { calls } = mockEngine({
      ...ownerRoutes,
      "PUT api/settings": ({ body }) => ({ ...SETTINGS, ...(body as object) }),
    });
    const user = userEvent.setup();
    renderApp("/settings");

    const deposit = await screen.findByLabelText(/Deposit/);
    expect(deposit).toHaveValue(0);
    expect(screen.getByRole("button", { name: "Save karo" })).toBeDisabled();
    await user.clear(deposit);
    await user.type(deposit, "500");
    await user.click(screen.getByRole("button", { name: "Save karo" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "api/settings")).toBe(true));
    const put = calls.find((c) => c.method === "PUT" && c.path === "api/settings");
    expect(put?.body).toEqual({ deposit_inr: 500 });
    expect(put?.query.get("pack")).toBe("dental_clinic");
    expect(await screen.findByText("Save ho gaya.")).toBeInTheDocument();
  });

  it("signs out everywhere through the engine and forgets the token", async () => {
    localStorage.setItem("haanji.token", "tok");
    const { calls } = mockEngine({ ...ownerRoutes, "POST api/auth/logout": () => ({ ok: true }) });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.click(await screen.findByRole("button", { name: /Sign out everywhere/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "api/auth/logout")).toBe(true));
    await waitFor(() => expect(localStorage.getItem("haanji.token")).toBeNull());
    await screen.findByRole("heading", { name: "Sign in" });
  });
});

describe("customers' data requests", () => {
  it("lists the requests and erases only after the owner confirms", async () => {
    localStorage.setItem("haanji.token", "tok");
    let status = "PENDING";
    const { calls } = mockEngine({
      ...ownerRoutes,
      "api/privacy/requests": () => ({ requests: [
        { request_id: "r1", kind: "erase", status, shown: "98XXXXX032", requested_at: "2026-11-18T04:00:00+00:00", decided_at: null, result: {} },
        { request_id: "r0", kind: "export", status: "DONE", shown: "98XXXXX031", requested_at: "2026-11-18T03:00:00+00:00", decided_at: "2026-11-18T03:00:00+00:00", result: {} },
      ] }),
      "POST api/privacy/requests/*": ({ body }) => { status = (body as { approve: boolean }).approve ? "ERASED" : "REJECTED"; return { request_id: "r1", kind: "erase", status, shown: "98XXXXX032", requested_at: "", decided_at: "", result: {} }; },
    });
    const user = userEvent.setup();
    renderApp("/settings");
    expect(await screen.findByText("98XXXXX032")).toBeInTheDocument();
    expect(screen.getByText("1 aapke intezaar mein")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mita do" }));
    expect(calls.some((c) => c.method === "POST" && c.path.startsWith("api/privacy/requests/"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Haan, mita do" }));
    await waitFor(() => expect(screen.getByText(/Mita diya. Receipts seal rehti hain/)).toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST" && c.path === "api/privacy/requests/r1")!;
    expect(post.body).toEqual({ approve: true });
    expect(post.query.get("pack")).toBe("dental_clinic");
  });
});

describe("devices and activity", () => {
  it("lists the signed-in devices, ends another one, and shows the owner's activity log", async () => {
    localStorage.setItem("haanji.token", "tok");
    let devices = [
      { sid: "s1", created: 1795000000, last_seen: 1795100000, agent: "Mozilla/5.0 (Linux; Android 14) Chrome/130.0", current: true },
      { sid: "s2", created: 1794000000, last_seen: 1794500000, agent: "Mozilla/5.0 (Macintosh; Mac OS X) Safari/605.1", current: false },
    ];
    const { calls } = mockEngine({
      ...ownerRoutes,
      "api/auth/sessions": () => ({ sessions: devices }),
      "DELETE api/auth/sessions/*": () => { devices = devices.filter((d) => d.sid !== "s2"); return { ok: true }; },
      "api/audit": () => ({ entries: [{ id: 1, at: 1795100000, phone: "9876543210", role: "owner", method: "PUT", path: "/api/settings", pack: "dental_clinic", status: 200 }] }),
    });
    const user = userEvent.setup();
    renderApp("/settings");
    expect(await screen.findByText("Android · Chrome")).toBeInTheDocument();
    expect(screen.getByText("Mac · Safari")).toBeInTheDocument();
    expect(await screen.findByText("PUT /api/settings · dental_clinic")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.queryByText("Mac · Safari")).toBeNull());
    expect(calls.some((c) => c.method === "DELETE" && c.path === "api/auth/sessions/s2")).toBe(true);
  });
});
