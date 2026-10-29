import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OWNER, STATUS_AUTH, mockEngine, renderApp } from "./mock";

describe("sign in", () => {
  it("asks for a code, verifies it, stores the token and opens the console", async () => {
    const { calls } = mockEngine({
      "api/status": () => STATUS_AUTH,
      "POST api/auth/otp": () => ({ sent: true, channel: "whatsapp" }),
      "POST api/auth/verify": () => ({ token: "tok-123", user: OWNER }),
      "api/auth/me": () => ({ enabled: true, user: OWNER }),
      "api/conversations": () => ({ conversations: [] }),
    });
    const user = userEvent.setup();
    renderApp("/calls");

    await screen.findByRole("heading", { name: "Sign in" });
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
});
