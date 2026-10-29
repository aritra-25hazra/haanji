import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { STATUS_OPEN, booking, mockEngine, renderApp } from "./mock";

describe("the public demo is read-only", () => {
  it("shows bookings but offers no cancel / no-show / completed when the engine says demo_readonly", async () => {
    mockEngine({
      "api/status": () => ({ ...STATUS_OPEN, demo_readonly: true, backup: { s3: false, restore_from: false } }),
      "api/bookings": () => ({ bookings: [booking({ booking_id: "b1" })] }),
      "api/waitlist": () => ({ waitlist: [] }),
      "api/payments": () => ({ payments: [] }),
    });
    renderApp("/calendar");
    const card = await screen.findByTestId("booking-b1");
    expect(within(card).getByText("root canal")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "No-show" })).toBeNull();
    expect(within(card).getByText(/read-only/)).toBeInTheDocument();
  });

  it("warns the owner when no backup is configured and keeps the settings form read-only", async () => {
    mockEngine({
      "api/status": () => ({ ...STATUS_OPEN, demo_readonly: true, backup: { s3: false, restore_from: false } }),
      "api/settings": () => ({ pack: "dental_clinic", settings: { reminders_on: true, reminder_hour_ist: 18, reminder_day_before: true, deposit_inr: 0, waitlist_on: true, digest_hour_ist: 20, language_script: "latin" } }),
      "api/google/status": () => ({ configured: false, connected: false, connected_at: null, redirect_uri: "" }),
      "api/digest": () => ({ pack: "dental_clinic", text: "", to: null, whatsapp_configured: false, hour_ist: 20 }),
      "api/auth/users": () => ({ users: [] }),
      "api/calendar/feed-url": () => ({ pack: "dental_clinic", url: "", webcal: "" }),
    });
    renderApp("/settings");
    expect(await screen.findByText(/redeploy par data jaata hai/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Read-only \(demo\)/ })).toBeDisabled();
  });
});
