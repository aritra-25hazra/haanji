import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OWNER, SETTINGS, STATUS_AUTH, fail, mockEngine, renderApp } from "./mock";

// Sign-in by email code, a password reset, and two-step sign-in with an
// authenticator app, as the console shows them (in Hindi, the default here).
const MAIL = { ...STATUS_AUTH, auth: { enabled: true, email_codes: true } };
const signedInRoutes = {
  "api/auth/me": () => ({ enabled: true, user: OWNER }),
  "api/conversations": () => ({ conversations: [] }),
};

describe("email codes and password reset", () => {
  it("offers no email code or reset link while the server cannot send mail", async () => {
    mockEngine({ "api/status": () => STATUS_AUTH });
    renderApp("/calls");
    await screen.findByRole("heading", { name: "Sign in" });
    expect(screen.queryByRole("button", { name: "Iske bajaye email pe code" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Password bhool gaye?" })).toBeNull();
  });

  it("signs in with a code sent by email", async () => {
    const { calls } = mockEngine({
      "api/status": () => MAIL,
      "POST api/auth/email-code": () => ({ sent: true }),
      "POST api/auth/email-verify": ({ body }) => ((body as { code: string }).code === "246810"
        ? { token: "tok-mail", user: OWNER } : fail(401, { detail: "wrong or expired code" })),
      ...signedInRoutes,
    });
    const user = userEvent.setup();
    renderApp("/calls");
    await user.click(await screen.findByRole("button", { name: "Iske bajaye email pe code" }));
    await user.type(screen.getByLabelText("Email"), "owner@clinic.in");
    await user.click(screen.getByRole("button", { name: /Code bhejo/ }));
    await screen.findByText(/Agar is email ka account hai/);
    expect(calls.find((c) => c.path === "api/auth/email-code")?.body).toEqual({ email: "owner@clinic.in", purpose: "login" });
    await user.type(screen.getByLabelText(/6 ankon ka code/), "246810");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    await waitFor(() => expect(localStorage.getItem("haanji.token")).toBe("tok-mail"));
    await screen.findByRole("heading", { name: "Calls" });
  });

  it("resets a forgotten password with an emailed code, then asks to sign in again", async () => {
    const { calls } = mockEngine({
      "api/status": () => MAIL,
      "POST api/auth/email-code": () => ({ sent: true }),
      "POST api/auth/reset": () => ({ ok: true }),
    });
    const user = userEvent.setup();
    renderApp("/calls");
    await user.click(await screen.findByRole("button", { name: "Password bhool gaye?" }));
    await user.type(screen.getByLabelText("Email"), "owner@clinic.in");
    await user.click(screen.getByRole("button", { name: /Reset code bhejo/ }));
    await user.type(await screen.findByLabelText(/6 ankon ka code/), "135790");
    const save = screen.getByRole("button", { name: "Naya password rakho" });
    await user.type(screen.getByLabelText(/Naya password/), "short");
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText(/Naya password/), "-but-longer");
    await user.click(save);
    expect(await screen.findByText(/Password badal gaya/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "api/auth/email-code")?.body).toEqual({ email: "owner@clinic.in", purpose: "reset" });
    expect(calls.find((c) => c.path === "api/auth/reset")?.body).toEqual({ email: "owner@clinic.in", code: "135790", password: "short-but-longer" });
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(localStorage.getItem("haanji.token")).toBeNull();
  });
});

describe("two-step sign-in", () => {
  it("stops after the password and asks for the app's code with the ticket", async () => {
    let tries = 0;
    const { calls } = mockEngine({
      "api/status": () => STATUS_AUTH,
      "POST api/auth/login": () => ({ needs_2fa: true, ticket: "tick-1" }),
      "POST api/auth/2fa/verify": () => (++tries === 1 ? fail(401, { detail: "that code is not right" }) : { token: "tok-2fa", user: OWNER }),
      ...signedInRoutes,
    });
    const user = userEvent.setup();
    renderApp("/calls");
    await user.type(await screen.findByLabelText("Email"), "owner@clinic.in");
    await user.type(screen.getByLabelText("Password"), "a-long-passphrase");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    const field = await screen.findByLabelText("App wala code");
    expect(localStorage.getItem("haanji.token")).toBeNull();
    await user.type(field, "000000");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    expect(await screen.findByText(/Code sahi nahi hai/)).toBeInTheDocument();
    await user.clear(field);
    await user.type(field, "123456");
    await user.click(screen.getByRole("button", { name: /Andar jao/ }));
    await waitFor(() => expect(localStorage.getItem("haanji.token")).toBe("tok-2fa"));
    expect(calls.filter((c) => c.path === "api/auth/2fa/verify").map((c) => c.body)).toEqual([
      { ticket: "tick-1", code: "000000" }, { ticket: "tick-1", code: "123456" }]);
  });

  it("is turned on in Settings with a QR, a first code, and recovery codes shown once", async () => {
    localStorage.setItem("haanji.token", "tok");
    let enabled = false;
    const { calls } = mockEngine({
      "api/status": () => STATUS_AUTH,
      "api/auth/me": () => ({ enabled: true, user: OWNER }),
      "api/settings": () => SETTINGS,
      "api/google/status": () => ({ configured: false, connected: false, connected_at: null, redirect_uri: "" }),
      "api/auth/users": () => ({ users: [OWNER] }),
      "api/auth/2fa": () => ({ enabled, recovery_codes_left: enabled ? 8 : 0 }),
      "POST api/auth/2fa/setup": () => ({ secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", uri: "otpauth://totp/x", qr_svg: "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>" }),
      "POST api/auth/2fa/enable": () => { enabled = true; return { enabled: true, recovery_codes: ["ab12-cd34", "ef56-0789"] }; },
    });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.click(await screen.findByRole("button", { name: /Two-step sign-in chalu karo/ }));
    const qr = await screen.findByRole("img", { name: "Authenticator app ke liye QR code" });
    expect(qr.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByText(/JBSW Y3DP/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("App wala code"), "123456");
    await user.click(screen.getByRole("button", { name: "Pakka karo" }));
    expect(await screen.findByText("ab12-cd34")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "api/auth/2fa/enable")?.body).toEqual({ code: "123456" });
    await user.click(screen.getByRole("button", { name: "Maine save kar liye" }));
    expect(await screen.findByText("chalu · 8 recovery codes bache")).toBeInTheDocument();
    expect(screen.queryByText("ab12-cd34")).toBeNull();
  });
});
