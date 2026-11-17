/* HaanJi — the pages' two languages, the same switch as the console's.
   English is written in the HTML (it shows without JS, and search engines read
   it); the Hindi (Roman Hinglish) sits beside it:
     data-hi="…"            the element's text in Hindi
     data-hi-html="…"       the element's inner HTML in Hindi (links, <b> inside)
     data-hi-alt / -title / -aria-label / -placeholder / -content   an attribute
   <div data-lang-switch></div> marks where the EN / हिं buttons go.
   The choice is localStorage "haanji.lang" (the console reads the same key),
   and ?lang=hi or ?lang=en in a link sets it.
   What HaanJi itself says is never translated here: it speaks the pack's language. */
(function (global) {
  "use strict";
  var KEY = "haanji.lang";
  var ATTRS = ["alt", "title", "aria-label", "placeholder", "content"];
  var english = new WeakMap();          // element -> {text|html|attrs} as written in English
  var listeners = [];

  function initial() {
    try {
      var q = new URLSearchParams(location.search).get("lang");
      if (q === "hi" || q === "en") { localStorage.setItem(KEY, q); return q; }
      return localStorage.getItem(KEY) === "hi" ? "hi" : "en";
    } catch (e) { return "en"; }
  }
  var lang = initial();

  function remember(el) {
    var e = english.get(el);
    if (!e) {
      e = { text: el.textContent, html: el.innerHTML, attrs: {} };
      ATTRS.forEach(function (a) { if (el.hasAttribute("data-hi-" + a)) e.attrs[a] = el.getAttribute(a); });
      english.set(el, e);
    }
    return e;
  }

  function apply(root) {
    root = root || document;
    var hi = lang === "hi";
    var sel = "[data-hi],[data-hi-html]," + ATTRS.map(function (a) { return "[data-hi-" + a + "]"; }).join(",");
    var els = Array.prototype.slice.call(root.querySelectorAll(sel));
    if (root.matches && root.matches(sel)) els.unshift(root);
    els.forEach(function (el) {
      var e = remember(el);
      if (!hi && !e.swapped) return;      // still the English it was written in
      e.swapped = true;
      if (el.hasAttribute("data-hi-html")) {
        el.innerHTML = hi ? el.getAttribute("data-hi-html") : e.html;
        if (global.Signboard && global.Signboard.mountIcons) global.Signboard.mountIcons(el);
      } else if (el.hasAttribute("data-hi")) {
        el.textContent = hi ? el.getAttribute("data-hi") : e.text;
      }
      ATTRS.forEach(function (a) {
        if (!el.hasAttribute("data-hi-" + a)) return;
        var v = hi ? el.getAttribute("data-hi-" + a) : e.attrs[a];
        if (v == null) el.removeAttribute(a); else el.setAttribute(a, v);
      });
    });
    document.documentElement.lang = hi ? "hi-Latn" : "en-IN";
    document.querySelectorAll("[data-lang-switch] button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === lang));
    });
  }

  function set(l) {
    lang = l === "hi" ? "hi" : "en";
    try { localStorage.setItem(KEY, lang); } catch (e) { /* not remembered */ }
    apply(document);
    listeners.forEach(function (f) { try { f(lang); } catch (e) { /* a page's own handler */ } });
  }

  function mountSwitch() {
    document.querySelectorAll("[data-lang-switch]").forEach(function (slot) {
      if (slot.firstChild) return;
      slot.className = (slot.className ? slot.className + " " : "") + "lang-switch";
      slot.setAttribute("role", "group");
      slot.setAttribute("aria-label", "Language / भाषा");
      [["en", "EN", "English"], ["hi", "हिं", "हिंदी (Hinglish)"]].forEach(function (o) {
        var b = document.createElement("button");
        b.type = "button";
        b.setAttribute("data-lang", o[0]);
        b.setAttribute("lang", o[0] === "hi" ? "hi" : "en");
        b.title = o[2];
        b.textContent = o[1];
        b.addEventListener("click", function () { set(o[0]); });
        slot.appendChild(b);
      });
    });
  }

  var css = ".lang-switch{display:inline-flex;align-items:center;border:1px solid currentColor;border-radius:999px;overflow:hidden;opacity:.9}"
    + ".lang-switch button{border:0;background:transparent;color:inherit;font:inherit;font-size:13px;font-weight:600;padding:0 12px;min-height:40px;min-width:44px;cursor:pointer}"
    + ".lang-switch button[aria-pressed=true]{background:var(--marigold,#F5B91E);color:var(--cobalt,#1B3B8C)}"
    + ".lang-switch button:focus-visible{outline:2px solid var(--marigold,#F5B91E);outline-offset:2px}";
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  global.HaanJiLang = {
    get: function () { return lang; },
    set: set,
    /** A string a page's script writes: English, or the Hindi beside it. */
    t: function (en, hi) { return lang === "hi" && hi ? hi : en; },
    apply: apply,
    onChange: function (f) { listeners.push(f); },
  };

  function start() { mountSwitch(); apply(document); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(window);
