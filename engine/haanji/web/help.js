/* The help assistant on the engine's own pages (the landing page): the same
 * /api/help/chat the console's widget uses. Claude or Gemini answer when the
 * server has their keys; quick built-in answers otherwise. Replies are put in
 * with textContent, never as HTML. Needs lang.js first. */
(function () {
  "use strict";
  var L = window.HaanJiLang || { t: function (en) { return en; }, get: function () { return "en"; }, onChange: function () {} };
  var T = function (en, hi) { return L.t(en, hi); };
  var NAMES = { claude: "Claude", gemini: "Gemini", faq: ["Quick answers", "Turant jawab"] };
  var name = function (p) { var n = NAMES[p]; return typeof n === "string" ? n : T(n[0], n[1]); };
  var STARTERS = [["What does HaanJi do?", "HaanJi kya karta hai?"], ["How do I try it?", "Kaise try karun?"],
                  ["How much does it cost?", "Kitne ka hai?"]];

  var css = document.createElement("style");
  css.textContent = [
    ".hj-fab{position:fixed;right:16px;bottom:16px;z-index:60;display:inline-flex;align-items:center;gap:8px;border:0;border-radius:999px;padding:10px 16px 10px 10px;background:var(--cobalt,#1B3B8C);color:var(--chalk,#FFF7E6);font:600 15px/1 var(--font-body,system-ui);cursor:pointer;box-shadow:0 6px 20px rgba(20,33,61,.3);min-height:44px}",
    ".hj-fab i{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--marigold,#F5B91E);color:var(--cobalt,#1B3B8C);font-style:normal;font-weight:800}",
    ".hj-fab:focus-visible,.hj-chat button:focus-visible,.hj-chat textarea:focus-visible{outline:3px solid var(--marigold,#F5B91E);outline-offset:2px}",
    ".hj-chat{position:fixed;right:16px;bottom:72px;z-index:61;width:min(380px,calc(100vw - 32px));max-height:min(540px,calc(100vh - 96px));display:grid;grid-template-rows:auto auto 1fr auto;background:#fff;color:#14213D;border-radius:14px;box-shadow:0 16px 48px rgba(20,33,61,.3);overflow:hidden;font:15px/1.45 var(--font-body,system-ui)}",
    ".hj-chat[hidden]{display:none}",
    ".hj-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:14px 14px 8px}",
    ".hj-head h2{margin:0;font:800 17px/1.2 var(--font-display,system-ui);color:#14213D}",
    ".hj-head p{margin:4px 0 0;font-size:12px;color:rgba(20,33,61,.68)}",
    ".hj-x{border:1px solid rgba(27,59,140,.2);background:#fff;border-radius:8px;width:32px;height:32px;cursor:pointer;color:#14213D}",
    ".hj-pick{display:flex;gap:6px;padding:0 14px 10px;border-bottom:1px solid rgba(27,59,140,.14)}",
    ".hj-pick button{border:1px solid rgba(27,59,140,.2);background:#fff;border-radius:999px;padding:4px 10px;font:inherit;font-size:12px;color:#14213D;cursor:pointer;min-height:28px}",
    ".hj-pick button[aria-checked=true]{background:#14213D;color:#fff;border-color:#14213D}",
    ".hj-pick button:disabled{opacity:.45;cursor:not-allowed}",
    ".hj-log{overflow-y:auto;padding:12px 14px;display:grid;gap:10px;align-content:start;min-height:120px}",
    ".hj-start{display:grid;gap:6px;justify-items:start}",
    ".hj-start button{border:1px solid rgba(27,59,140,.25);background:#fff;border-radius:999px;padding:6px 12px;font:inherit;font-size:13px;color:#1B3B8C;cursor:pointer}",
    ".hj-msg{max-width:88%;display:grid;gap:2px}.hj-msg p{margin:0;padding:8px 11px;border-radius:12px;white-space:pre-wrap;font-size:14px}",
    ".hj-msg.user{justify-self:end}.hj-msg.user p{background:#1B3B8C;color:#fff}.hj-msg.bot p{background:rgba(27,59,140,.07)}",
    ".hj-msg small{font-size:11px;color:rgba(20,33,61,.6);padding:0 4px}.hj-err{margin:0;color:#B8371F;font-size:13px}",
    ".hj-form{display:flex;gap:8px;align-items:flex-end;padding:10px 14px 14px;border-top:1px solid rgba(27,59,140,.14)}",
    ".hj-form textarea{flex:1;resize:none;font:inherit;font-size:14px;border:1px solid rgba(27,59,140,.25);border-radius:10px;padding:8px 10px;color:#14213D;background:#fff}",
    ".hj-form button{border:0;border-radius:10px;padding:9px 14px;background:var(--marigold,#F5B91E);color:#102A66;font:700 14px/1 var(--font-body,system-ui);cursor:pointer;min-height:38px}",
    ".hj-form button:disabled{opacity:.5;cursor:not-allowed}",
    ".hj-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}",
    "@media print{.hj-fab,.hj-chat{display:none}}"
  ].join("\n");
  document.head.appendChild(css);

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  var msgs = [], providers = null, provider = "faq", busy = false;
  var fab = el("button", "hj-fab"); fab.type = "button"; fab.setAttribute("aria-expanded", "false"); fab.setAttribute("aria-controls", "hj-chat");
  var fabI = el("i", null, "?"); fabI.setAttribute("aria-hidden", "true"); var fabT = el("span");
  fab.appendChild(fabI); fab.appendChild(fabT);
  var box = el("section", "hj-chat"); box.id = "hj-chat"; box.hidden = true; box.setAttribute("role", "dialog");
  var head = el("div", "hj-head"), headText = el("div"), h2 = el("h2"), sub = el("p"), x = el("button", "hj-x", "×");
  x.type = "button"; headText.appendChild(h2); headText.appendChild(sub); head.appendChild(headText); head.appendChild(x);
  var pick = el("div", "hj-pick"); pick.setAttribute("role", "radiogroup");
  var log = el("div", "hj-log"); log.setAttribute("aria-live", "polite");
  var form = el("form", "hj-form"), label = el("label", "hj-sr"), ta = el("textarea"), send = el("button");
  ta.id = "hj-q"; ta.rows = 2; ta.maxLength = 1200; label.htmlFor = "hj-q"; send.type = "submit";
  form.appendChild(label); form.appendChild(ta); form.appendChild(send);
  box.appendChild(head); box.appendChild(pick); box.appendChild(log); box.appendChild(form);
  document.body.appendChild(box); document.body.appendChild(fab);

  function words() {
    fabT.textContent = T("Questions?", "Sawaal?");
    box.setAttribute("aria-label", T("Help assistant", "Help assistant"));
    h2.textContent = T("Ask about HaanJi", "HaanJi ke baare mein poochho");
    sub.textContent = T("Answers about the product and the demo. Do not share personal details.", "Product aur demo ke baare mein jawab. Apni personal details mat daalo.");
    x.setAttribute("aria-label", T("Close", "Band karo"));
    pick.setAttribute("aria-label", T("Who answers", "Kaun jawab de"));
    label.textContent = T("Your question", "Aapka sawaal");
    ta.placeholder = T("Ask in English or Hinglish…", "English ya Hinglish mein poochho…");
    send.textContent = T("Send", "Bhejo");
    drawPick(); drawLog();
  }
  function drawPick() {
    pick.textContent = "";
    ["claude", "gemini", "faq"].forEach(function (p) {
      var on = providers ? providers.indexOf(p) >= 0 : p === "faq";
      var b = el("button", null, name(p)); b.type = "button"; b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(provider === p)); b.disabled = !on;
      if (!on) b.title = T("Switches on when the server has a " + name(p) + " key", "Server mein " + name(p) + " key daalne pe on hoga");
      b.addEventListener("click", function () { provider = p; drawPick(); });
      pick.appendChild(b);
    });
  }
  function drawLog(error) {
    log.textContent = "";
    if (!msgs.length) {
      var s = el("div", "hj-start");
      STARTERS.forEach(function (q) { var b = el("button", null, T(q[0], q[1])); b.type = "button"; b.addEventListener("click", function () { ask(T(q[0], q[1])); }); s.appendChild(b); });
      log.appendChild(s);
    }
    msgs.forEach(function (m) {
      var d = el("div", "hj-msg " + (m.role === "user" ? "user" : "bot")); d.appendChild(el("p", null, m.content));
      if (m.by) d.appendChild(el("small", null, name(m.by)));
      log.appendChild(d);
    });
    if (busy) { var w = el("div", "hj-msg bot"); w.appendChild(el("p", null, T("Thinking…", "Soch raha hai…"))); log.appendChild(w); }
    if (error) { var e = el("p", "hj-err", error); e.setAttribute("role", "alert"); log.appendChild(e); }
    log.scrollTop = log.scrollHeight;
    send.disabled = busy;
  }
  function ask(q) {
    q = (q || "").trim();
    if (!q || busy) return;
    msgs.push({ role: "user", content: q }); ta.value = ""; busy = true; drawLog();
    fetch("api/help/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: msgs.map(function (m) { return { role: m.role, content: m.content }; }),
                             provider: provider, lang: L.get() === "hi" ? "hi" : "en", page: location.pathname }) })
      .then(function (r) { if (!r.ok) throw new Error(r.status === 429 ? T("Too many questions; wait a minute.", "Bahut saare sawaal; ek minute ruko.") : "HTTP " + r.status); return r.json(); })
      .then(function (r) { busy = false; msgs.push({ role: "assistant", content: r.reply, by: r.provider }); drawLog(); })
      .catch(function (e) { busy = false; drawLog(e.message && e.message.indexOf("HTTP") !== 0 ? e.message : T("The server may be waking up. Try again in a minute.", "Server shayad jaag raha hai. Ek minute mein dobara try karo.")); });
  }
  function open() {
    box.hidden = false; fab.setAttribute("aria-expanded", "true"); ta.focus();
    if (!providers) fetch("api/help/status").then(function (r) { return r.json(); }).then(function (s) {
      providers = s.providers || ["faq"]; provider = providers[0] || "faq"; drawPick();
    }).catch(function () { providers = ["faq"]; drawPick(); });
  }
  function close() { box.hidden = true; fab.setAttribute("aria-expanded", "false"); fab.focus(); }
  fab.addEventListener("click", function () { box.hidden ? open() : close(); });
  x.addEventListener("click", close);
  box.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(ta.value); });
  ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });
  words();
  L.onChange(words);
})();
