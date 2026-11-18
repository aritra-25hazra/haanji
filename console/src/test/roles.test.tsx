import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OWNER, SETTINGS, STAFF, STATUS_AUTH, mockEngine, renderApp } from "./mock";

const PACKS = { packs: [{ pack_id: "dental_clinic", display_name: "Dental clinic", version: 3, language: "hinglish", services: 6, staff: 2, scenarios: 6, issues: [] }] };

describe("role gating", () => {
  it("hides the Settings link and page from staff", async () => {
    localStorage.setItem("haanji.token", "tok");
    mockEngine({ "api/status": () => STATUS_AUTH, "api/auth/me": () => ({ enabled: true, user: STAFF }) });
    renderApp("/settings");
    expect(await screen.findByText("Yeh page sirf owner ke liye hai.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).toBeNull();
    expect(screen.getByRole("link", { name: "Calendar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toBeInTheDocument();
  });

  it("shows the Admin menu to the owner and never to staff", async () => {
    localStorage.setItem("haanji.token", "tok");
    mockEngine({ "api/status": () => STATUS_AUTH, "api/auth/me": () => ({ enabled: true, user: STAFF }), "api/conversations": () => ({ conversations: [] }) });
    const staff = renderApp("/calls");
    await screen.findByRole("link", { name: "Calendar" });
    expect(screen.queryByRole("button", { name: "Admin ke pages" })).toBeNull();
    staff.unmount();
    localStorage.setItem("haanji.token", "tok");
    mockEngine({ "api/status": () => STATUS_AUTH, "api/auth/me": () => ({ enabled: true, user: OWNER }), "api/conversations": () => ({ conversations: [] }) });
    renderApp("/calls");
    expect(await screen.findByRole("button", { name: "Admin ke pages" })).toBeInTheDocument();
  });

  it("hides the pack save from staff in the studio", async () => {
    localStorage.setItem("haanji.token", "tok");
    mockEngine({
      "api/status": () => STATUS_AUTH,
      "api/auth/me": () => ({ enabled: true, user: STAFF }),
      "api/packs": () => PACKS,
      "api/packs/dental_clinic": () => ({ pack_id: "dental_clinic", yaml: "display_name: Dental clinic\n" }),
    });
    renderApp("/studio");
    await screen.findByLabelText("Pack YAML");
    expect(screen.queryByRole("button", { name: /Validate & save/ })).toBeNull();
    expect(screen.getByText("save sirf owner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeInTheDocument();
  });

  it("shows the owner everything", async () => {
    localStorage.setItem("haanji.token", "tok");
    mockEngine({
      "api/status": () => STATUS_AUTH,
      "api/auth/me": () => ({ enabled: true, user: OWNER }),
      "api/settings": () => SETTINGS,
      "api/auth/users": () => ({ users: [OWNER, STAFF] }),
    });
    renderApp("/settings");
    expect(await screen.findByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Sign out everywhere/ })).toBeInTheDocument();
    expect(await screen.findByText("Ravi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hatao" })).toBeInTheDocument();   // staff can be removed, never yourself
    expect(screen.getByText("aap")).toBeInTheDocument();
  });
});
