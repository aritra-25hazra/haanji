import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { getLang, setLang } from "../i18n";
import { MEASURED } from "../results";
import { STATUS_OPEN, mockEngine, renderApp } from "./mock";

// The rest of the suite reads the Hindi words (test/setup.ts); these tests
// are about English being the default and the switch between the two.
beforeEach(() => { setLang("en"); });

describe("English by default, Hindi on the switch", () => {
  it("shows the frame in English and switches every word to Hindi and back", async () => {
    mockEngine({ "api/status": () => STATUS_OPEN, "api/conversations": () => ({ conversations: [] }) });
    renderApp("/calls");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Today" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "हिं" }));
    expect(getLang()).toBe("hi");
    expect(within(nav).getByRole("link", { name: "Aaj" })).toBeInTheDocument();
    expect(localStorage.getItem("haanji.lang")).toBe("hi");
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(within(nav).getByRole("link", { name: "Today" })).toBeInTheDocument();
  });

  it("says the engine is waking up in English, with the way to the sample shop", async () => {
    mockEngine({ "api/status": () => { throw new TypeError("fetch failed"); } });
    renderApp("/calls");      // the dashboard's chart needs a ResizeObserver jsdom does not have
    expect(await screen.findByText(/The engine is waking up/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "See the sample meanwhile" }));
    expect(await screen.findByText(/a made-up shop with 100 customers/)).toBeInTheDocument();
  });
});

describe("the front door and How it works", () => {
  it("opens on what HaanJi does and the three measured ideas, numbers from the benchmark", async () => {
    mockEngine({ "api/status": () => STATUS_OPEN });
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: /answers every call/ })).toBeInTheDocument();
    const led = MEASURED.ledger;
    expect(screen.getByText(`${led.mutations_detected} / ${led.mutations_attempted}`)).toBeInTheDocument();
    expect(screen.getByText(/simulated calls, not live customers/)).toBeInTheDocument();
    expect(screen.getAllByText("Price on request")).toHaveLength(3);
    expect(screen.queryByText(/₹\d/)).toBeNull();
  });

  it("offers a WhatsApp demo button only when the engine has a sales number", async () => {
    mockEngine({ "api/status": () => ({ ...STATUS_OPEN, sales_whatsapp: "+91 98765 00000" }) });
    renderApp("/");
    const link = await screen.findByRole("link", { name: /Ask for a demo on WhatsApp/ });
    expect(link.getAttribute("href")).toMatch(/^https:\/\/wa\.me\/919876500000\?text=/);
  });

  it("shows the measured table and runs the shop's scenarios on the live engine", async () => {
    const { calls } = mockEngine({
      "api/status": () => STATUS_OPEN,
      "POST api/packs/*/selftest": () => ({ ok: true, summary: "4/4 passed", results: [{ passed: true, line: "books a cleaning" }] }),
    });
    renderApp("/how");
    expect(await screen.findByRole("heading", { name: "What the benchmark measured" })).toBeInTheDocument();
    expect(screen.getByText(MEASURED.how_to_reproduce)).toBeInTheDocument();
    const run = await screen.findByRole("button", { name: /Run \d+ scenarios/ });
    await act(async () => { fireEvent.click(run); });
    expect(await screen.findByText("books a cleaning")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "api/packs/dental_clinic/selftest")).toBe(true);
  });
});

describe("the help assistant", () => {
  it("asks the engine with the picked model, the page and the language, and says who answered", async () => {
    const { calls } = mockEngine({
      "api/status": () => STATUS_OPEN,
      "api/conversations": () => ({ conversations: [] }),
      "api/help/status": () => ({ providers: ["gemini", "faq"], models: {}, daily_limit: 100, used_today: 0 }),
      "POST api/help/chat": () => ({ reply: "Open Calendar and pick a slot.", provider: "gemini", model: "gemini-x" }),
    });
    renderApp("/calls");
    fireEvent.click(await screen.findByRole("button", { name: /Help/ }));
    const dialog = await screen.findByRole("dialog", { name: "Help assistant" });
    expect(await within(dialog).findByRole("radio", { name: "Gemini" })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByRole("radio", { name: "Claude" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Your question"), { target: { value: "how to book?" } });
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Send" })); });
    expect(await within(dialog).findByText("Open Calendar and pick a slot.")).toBeInTheDocument();
    const sent = calls.find((c) => c.path === "api/help/chat")!.body as { provider: string; page: string; lang: string; messages: unknown[] };
    expect(sent).toMatchObject({ provider: "gemini", page: "/calls", lang: "en" });
    expect(sent.messages).toEqual([{ role: "user", content: "how to book?" }]);
  });
});

describe("who answers calls is said plainly", () => {
  it("names the built-in rules by default and a hosted model when one is on", async () => {
    mockEngine({ "api/status": () => STATUS_OPEN, "api/conversations": () => ({ conversations: [] }) });
    renderApp("/calls");
    expect(await screen.findByText("AI: built-in rules")).toBeInTheDocument();
  });

  it("says Gemini when the engine runs on Gemini", async () => {
    mockEngine({ "api/status": () => ({ ...STATUS_OPEN, dialogue: { provider: "gemini", model: "gemini-x" } }),
                 "api/conversations": () => ({ conversations: [] }) });
    renderApp("/calls");
    expect(await screen.findByText("AI: Gemini")).toBeInTheDocument();
  });
});
