import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { setLang } from "../i18n";

// jsdom has no matchMedia; gsap's ScrollTrigger asks for it when the React
// Bits components load. A media query that never matches is what a test wants.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => undefined, removeListener: () => undefined,
    addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false,
  });
}

// The behaviour tests were written against the Hindi words and still read
// them; test/i18n.test.ts and test/english.test.tsx cover English.
beforeEach(() => { setLang("hi"); });

afterEach(() => {
  cleanup();
  localStorage.clear();
});
