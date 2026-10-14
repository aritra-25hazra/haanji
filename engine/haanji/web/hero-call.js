/* The landing hero: one real call from the README, replayed on a loop. */
(function () {
  "use strict";
  const S = window.Signboard;
  const root = document.getElementById("hero-call");
  if (!root || !S) return;

  const SCRIPT = [
    { who: "agent", text: "Haanji, Smile Care Dental. Main aapki kya madad karun?" },
    { who: "caller", text: "haan ji mujhe rut kanal karwana tha",
      repair: { from_token: "rut kanal", to_surface: "root canal", asr_confidence: 0.32 } },
    { who: "agent", text: "Theek hai. Kis din ka time dekhun?", ms: 22 },
    { who: "caller", text: "kal subah ka time mil jayega",
      chip: { kind: "spec", text: "check_availability — pehle se taiyaar" } },
    { who: "agent", text: "Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath. Ya phir subah saade 10 baje. Chalega?", ms: 31 },
    { who: "caller", text: "haan confirm kar do", chip: { kind: "tool", text: "book_appointment" } },
    { who: "agent", text: "Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath. Confirmation code 2504-7863.",
      stamp: "RECEIPT 2504-7863" },
  ];
  const GAP = 900, TYPING = 500, HOLD = 2500;

  const log = root.querySelector(".transcript");
  const tm = S.timer(root.querySelector(".timer"));
  let paused = false;
  root.addEventListener("mouseenter", function () { paused = true; });
  root.addEventListener("mouseleave", function () { paused = false; });
  root.addEventListener("focusin", function () { paused = true; });
  root.addEventListener("focusout", function () { paused = false; });

  const sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  async function wait(ms) { await sleep(ms); while (paused) await sleep(120); }

  function bubble(line) {
    const b = document.createElement("div");
    b.className = "bubble " + line.who;
    b.textContent = line.text;
    const meta = document.createElement("div");
    meta.className = "meta";
    if (line.repair) meta.appendChild(S.repairNode(line.repair));
    if (line.chip) {
      const c = document.createElement("span");
      c.className = "chip chip-" + line.chip.kind;
      c.innerHTML = (line.chip.kind === "spec" ? S.icon("bolt") : "") + S.esc(line.chip.text);
      meta.appendChild(c);
    }
    if (line.ms) { const m = document.createElement("span"); m.className = "mono muted"; m.textContent = line.ms + " ms"; meta.appendChild(m); }
    if (line.stamp) { const st = document.createElement("span"); st.className = "stamp"; st.textContent = line.stamp; st.style.opacity = "0"; meta.appendChild(st); }
    if (meta.children.length) b.appendChild(meta);
    return b;
  }

  function renderStatic() {
    SCRIPT.forEach(function (l) {
      const b = bubble(l);
      log.appendChild(b);
      b.querySelectorAll(".repair").forEach(function (r) { r.classList.add("in"); });
      b.querySelectorAll(".stamp").forEach(function (s) { s.style.opacity = ""; });
    });
    root.querySelector(".timer").textContent = "00:41";
  }

  async function play() {
    for (;;) {
      log.innerHTML = "";
      tm.start();
      for (const line of SCRIPT) {
        if (line.who === "agent") { const t = S.typingDots(); log.appendChild(t); log.scrollTop = log.scrollHeight; await wait(TYPING); t.remove(); }
        const b = bubble(line);
        log.appendChild(b);
        log.scrollTop = log.scrollHeight;
        const r = b.querySelector(".repair");
        if (r) { await wait(350); await S.paintRepair(r); }
        const st = b.querySelector(".stamp");
        if (st) { await wait(300); await S.stamp(st); }
        await wait(GAP);
      }
      tm.stop();
      await wait(HOLD);
      const fade = log.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: "cubic-bezier(.4,0,1,1)" });
      await fade.finished.catch(function () {});
      fade.cancel();
    }
  }

  if (S.REDUCED) renderStatic(); else play();
})();
