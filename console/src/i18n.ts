/**
 * The console's two languages. English is the default; Hindi is the shop's
 * everyday Hinglish, in Roman script (the way owners type on WhatsApp).
 *
 * Every string a screen shows is written in English and passed through `t()`.
 * The Hindi words live in ./hi/*.ts, keyed by that English string. A string
 * inside a constant (a nav label, an outcome name) is marked with `en()` so
 * the coverage test can find it; `t()` is applied where it is shown.
 *
 * The agent's own voice (greetings, transcripts) is not translated here: it
 * speaks the pack's language whatever the console is set to.
 */
import { useSyncExternalStore } from "react";
import { HI } from "./hi";

export type Lang = "en" | "hi";
export const LANGS: { id: Lang; label: string; short: string }[] = [
  { id: "en", label: "English", short: "EN" },
  { id: "hi", label: "हिंदी (Hinglish)", short: "हिं" },
];
const KEY = "haanji.lang";

function initial(): Lang {
  try {
    const q = new URLSearchParams(window.location.search).get("lang");
    if (q === "hi" || q === "en") { localStorage.setItem(KEY, q); return q; }
    return localStorage.getItem(KEY) === "hi" ? "hi" : "en";
  } catch { return "en"; }
}

let current: Lang = typeof window === "undefined" ? "en" : initial();
const listeners = new Set<() => void>();
const mark = () => { if (typeof document !== "undefined") document.documentElement.lang = current === "hi" ? "hi-Latn" : "en-IN"; };
mark();

export function getLang(): Lang { return current; }
export function setLang(l: Lang): void {
  current = l;
  try { localStorage.setItem(KEY, l); } catch { /* not remembered */ }
  mark();
  listeners.forEach((f) => f());
}
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f); }; };

/** The current language; a component that calls it re-renders when it changes. */
export function useLang(): Lang { return useSyncExternalStore(subscribe, getLang, getLang); }

type Vars = Record<string, string | number>;
const fill = (s: string, vars?: Vars) => (vars ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : s);

/** Translate an English UI string. `{name}` placeholders are filled from `vars`. */
export function t(en: string, vars?: Vars): string {
  return fill(current === "hi" ? HI[en] ?? en : en, vars);
}
/** Marks an English string kept in a constant; it is translated where shown, with `t()`. */
export const en = (s: string) => s;

/** For components: re-render on a language change and get `t`. */
export function useT(): typeof t { useLang(); return t; }
