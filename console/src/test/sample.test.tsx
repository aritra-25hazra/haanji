import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { down, mockEngine, never, renderApp } from "./mock";

describe("sample data", () => {
  it("shows the SAMPLE banner and sample rows only in the public demo (engine away, nobody signed in)", async () => {
    mockEngine({ "api/status": down });
    renderApp("/calls");
    await screen.findByTestId("sample-banner");
    expect(screen.getByText("SAMPLE")).toBeInTheDocument();
    expect(await screen.findByText("98XXXXXX10")).toBeInTheDocument();
    expect(screen.queryByTestId("offline-banner")).toBeNull();
  });

  it("never substitutes sample data when a token exists", async () => {
    localStorage.setItem("haanji.token", "tok");
    mockEngine({ "api/status": down });
    renderApp("/calls");
    await screen.findByTestId("offline-banner");
    expect(screen.getByText("OFFLINE")).toBeInTheDocument();
    expect(screen.queryByTestId("sample-banner")).toBeNull();
    expect(screen.queryByText("98XXXXXX10")).toBeNull();
    expect(screen.queryByText("Sample calls")).toBeNull();
  });

  it("shows a checking state, not sample data, while the status call is pending", async () => {
    mockEngine({ "api/status": never });
    renderApp("/calls");
    expect(await screen.findByText("Engine check ho raha hai…")).toBeInTheDocument();
    expect(screen.queryByTestId("sample-banner")).toBeNull();
    expect(screen.queryByText("98XXXXXX10")).toBeNull();
  });
});
