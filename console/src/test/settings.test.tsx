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
