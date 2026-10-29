import { defineConfig } from "eslint/config";
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default defineConfig(
  { ignores: ["dist/**", "node_modules/**", "public/**", "coverage/**"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  // The two shared modules export formatters and hooks beside components on
  // purpose (the console's convention since v0.4); the rule is about Fast
  // Refresh granularity, not correctness, and every page imports from them.
  { files: ["src/components/Common.tsx", "src/state.tsx"], rules: { "react-refresh/only-export-components": "off" } },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}", "*.config.{js,ts}", "eslint.config.js"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
);
