import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { today } from "../dates";
import { STATUS_OPEN, booking, mockEngine, renderApp } from "./mock";

describe("calendar", () => {
  it("renders the day's bookings by staff and cancels one through the engine", async () => {
    const b1 = booking({ booking_id: "b1" });
    const b2 = booking({ booking_id: "b2", staff: "Dr Mehta", service: "cleaning", customer_name: "Pooja Verma", time: "11:00", paid: true, deposit_inr: 300, receipt_code: "1F3A-90C2" });
    const { calls } = mockEngine({
      "api/status": () => STATUS_OPEN,
      "api/bookings": () => ({ bookings: [b1, b2] }),
      "api/waitlist": () => ({ waitlist: [] }),
      "api/payments": () => ({ payments: [] }),
      "POST api/bookings/*/cancel": () => ({ ok: true }),
    });
    const user = userEvent.setup();
    renderApp("/calendar");

    expect(await screen.findByText("root canal")).toBeInTheDocument();
    expect(screen.getByText("Vijay Sharma")).toBeInTheDocument();
    expect(screen.getByText("2504-7863")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Dr Sheikh" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Dr Mehta" })).toBeInTheDocument();
    expect(screen.getByText(/₹500 baaki/)).toBeInTheDocument();
    expect(screen.getByText(/paid ₹300/)).toBeInTheDocument();

    const req = calls.find((c) => c.path === "api/bookings");
    expect(req?.query.get("pack")).toBe("dental_clinic");
    expect(req?.query.get("from")).toBe(today());
    expect(req?.query.get("to")).toBe(today());

    const card = screen.getByTestId("booking-b1");
    await user.click(within(card).getByRole("button", { name: "Cancel" }));
    await user.click(within(card).getByRole("button", { name: "Haan, cancel karo" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "api/bookings/b1/cancel")).toBe(true));
    expect(calls.find((c) => c.path === "api/bookings/b1/cancel")?.query.get("pack")).toBe("dental_clinic");
    expect(await screen.findByText(/Cancel ho gaya/)).toBeInTheDocument();
  });

  it("asks for a whole week in week view", async () => {
    const { calls } = mockEngine({
      "api/status": () => STATUS_OPEN,
      "api/bookings": () => ({ bookings: [] }),
      "api/waitlist": () => ({ waitlist: [] }),
      "api/payments": () => ({ payments: [] }),
    });
    const user = userEvent.setup();
    renderApp("/calendar");
    await screen.findByText("Is din koi booking nahi.");
    await user.click(screen.getByRole("button", { name: "Hafta" }));
    await waitFor(() => {
      const weekReq = calls.filter((c) => c.path === "api/bookings").at(-1);
      expect(weekReq?.query.get("from")).not.toBe(weekReq?.query.get("to"));
    });
  });
});
