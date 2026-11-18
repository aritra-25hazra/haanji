import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OWNER, STATUS_AUTH, fail, mockEngine, renderApp } from "./mock";

describe("sign in", () => {
  it("asks for a code, verifies it, stores the token and opens the console", async () => {
    const { calls } = mockEngine({
      "api/status": () => ({ ...STATUS_AUTH, whatsapp: { configured: true, number: "+91 98000 00000" } }),
      "POST api/auth/otp": () => ({ sent: true, channel: "whatsapp" }),
      "POST api/auth/verify": () => ({ token: "tok-123", user: OWNER }),
      "api/auth/me": () => ({ enabled: true, user: OWNER }),
      "api/conversations": () => ({ conversations: [] }),
    });
    const user = userEvent.setup();
    renderApp("/calls");

    await screen.findByRole("heading", { name: "Sign in" });
    await user.click(screen.getByRole("button", { name: "Iske bajaye WhatsApp code se" }));
    await user.type(screen.getByLabelText("WhatsApp number"), "9876543210");
    await user.click(screen.getByRole("button", { name: /Code bhejo/ }));
    await screen.findByText(/Code WhatsApp pe bheja/);
    expect(calls.find((c) => c.path === "api/auth/otp")?.body).toEqual({ phone: "9876543210" });

    await user.type(screen.getByLabelText(/6-digit code/), "123456");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    await waitFor(() => expect(localStorage.getItem("haanji.token")).toBe("tok-123"));
    expect(calls.find((c) => c.path === "api/auth/verify")?.body).toEqual({ phone: "9876543210", code: "123456" });

    // Signed in: the console shows, and later calls carry the token.
    await screen.findByRole("heading", { name: "Calls" });
    expect(screen.getByText("Asha")).toBeInTheDocument();
  });

  it("signs in with email and password, and offers no WhatsApp code while WhatsApp cannot deliver", async () => {
    const { calls } = mockEngine({
      "api/status": () => ({ ...STATUS_AUTH, whatsapp: { configured: true, number: "+1 (555) 620-0856", last_send: { delivery: { status: "failed", code: 131031 } } } }),
      "POST api/auth/login": ({ body }) => ((body as { password: string }).password === "correct horse"
        ? { token: "tok-email", user: { ...OWNER, email: "owner@clinic.in" } }
        : fail(401, { detail: "wrong email or password" })),
      "api/auth/me": () => ({ enabled: true, user: OWNER }),
      "api/conversations": () => ({ conversations: [] }),
    });
    const user = userEvent.setup();
    renderApp("/calls");
    await screen.findByRole("heading", { name: "Sign in" });
    expect(screen.queryByRole("button", { name: "Iske bajaye WhatsApp code se" })).toBeNull();
    await user.type(screen.getByLabelText("Email"), "owner@clinic.in");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    expect(await screen.findByText("Email ya password galat hai.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "correct horse");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    await waitFor(() => expect(localStorage.getItem("haanji.token")).toBe("tok-email"));
    expect(calls.filter((c) => c.path === "api/auth/login").map((c) => c.body)).toEqual([
      { email: "owner@clinic.in", password: "wrong" }, { email: "owner@clinic.in", password: "correct horse" }]);
    await screen.findByRole("heading", { name: "Calls" });
  });

  it("lets a visitor try the made-up demo shop without an account", async () => {
    mockEngine({ "api/status": () => STATUS_AUTH });
    const user = userEvent.setup();
    renderApp("/calls");
    await user.click(await screen.findByRole("button", { name: "Demo dekho (bina account)" }));
    expect(await screen.findByTestId("sample-banner")).toBeInTheDocument();
  });
});
