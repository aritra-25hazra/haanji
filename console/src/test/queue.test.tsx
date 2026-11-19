import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STATUS_OPEN, booking, mockEngine, renderApp } from "./mock";

const token = (over: Record<string, unknown> = {}) => ({
  token_id: "t1", label: "GP-01", staff: "Dr Mehta", department: "General Physician", number: 1, kind: "booked",
  booking_id: "b1", service: "general consultation", name: "Ravi", phone: "9811155501", status: "waiting",
  created_at: "2026-11-20T09:00:00+05:30", called_at: null, done_at: null, ...over,
});

const view = (over: Record<string, unknown> = {}) => ({
  day: "2026-11-20",
  lines: [
    { staff: "Dr Mehta", department: "General Physician", code: "GP", serving: null, waiting: [token()], done: 0, no_show: 0, avg_minutes: 15 },
    { staff: "Dr Joshi", department: "Paediatrics", code: "PD", serving: null, waiting: [], done: 0, no_show: 0, avg_minutes: 20 },
  ],
  to_check_in: [booking({ booking_id: "b2", customer_name: "Asha", staff: "Dr Mehta", time: "11:00" })],
  ...over,
});

describe("queue", () => {
  it("shows each doctor's line by department, checks a booked patient in and calls the next token", async () => {
    const { calls } = mockEngine({
      "api/status": () => STATUS_OPEN,
      "api/queue": () => view(),
      "POST api/queue/checkin": () => token({ token_id: "t2", label: "GP-02", booking_id: "b2", name: "Asha" }),
      "POST api/queue/next": () => ({ staff: "Dr Mehta", serving: token({ status: "serving" }) }),
    });
    const user = userEvent.setup();
    renderApp("/queue");

    expect(await screen.findByText("General Physician")).toBeInTheDocument();
    expect(screen.getByText("Paediatrics")).toBeInTheDocument();
    expect(screen.getByTestId("line-Dr Mehta")).toHaveTextContent("GP-01");

    await user.click(screen.getByRole("button", { name: "Check-in karo" }));
    expect(await screen.findByText(/Asha ka token GP-02 hai/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "api/queue/checkin")?.body).toEqual({ booking_id: "b2" });

    const next = screen.getAllByRole("button", { name: "Agla patient" });
    await user.click(next[0]!);
    await waitFor(() => expect(calls.find((c) => c.path === "api/queue/next")?.body).toEqual({ staff: "Dr Mehta" }));
    expect(await screen.findByText(/ab GP-01 ki baari/)).toBeInTheDocument();
  });

  it("shows a made-up queue in sample mode, by department, that cannot be changed", async () => {
    localStorage.setItem("haanji.sample", "1");
    mockEngine({ "api/status": () => ({ ...STATUS_OPEN, default_pack: "smile_care_clinic", packs: ["smile_care_clinic", "pragati_classes"] }) });
    renderApp("/queue");
    expect(await screen.findByTestId("sample-banner")).toBeInTheDocument();
    expect(await screen.findByText("General Physician")).toBeInTheDocument();
    expect(screen.getByText("Orthopaedics")).toBeInTheDocument();
    for (const b of screen.getAllByRole("button", { name: "Agla patient" })) expect(b).toBeDisabled();
  });
});
