import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component tests run in jsdom against a mocked fetch (src/test/mock.tsx);
// no engine is needed. Pure helpers are tested in node the same way.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    unstubGlobals: true,
    restoreMocks: true,
  },
});
