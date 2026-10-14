/* HaanJi — shared behaviours for the Signboard pages. Plain ES2020, no build.
   Everything hangs off window.Signboard; pages call what they need. */
(function (global) {
  "use strict";

  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // One icon family (Lucide-style strokes). Inline SVG so colour follows the text.
  const PHONE = '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6.2 6.2l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>';
  const ICONS = {
    phone: PHONE,
    phoneMissed: '<line x1="23" y1="1" x2="17" y2="7"/><line x1="17" y1="1" x2="23" y2="7"/>' + PHONE,
    mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
    micOff: '<line x1="2" y1="2" x2="22" y2="22"/><path d="M18.9 13.4A7 7 0 0 0 19 12v-2"/><path d="M5 10v2a7 7 0 0 0 12 5"/><path d="M15 9.3V5a3 3 0 0 0-5.9-.7"/><path d="M9 9v3a3 3 0 0 0 5.1 2.1"/><line x1="12" y1="19" x2="12" y2="22"/>',
    speaker: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/>',
    speakerOff: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>',
    bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    chevron: '<polyline points="6 9 12 15 18 9"/>',
    send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    github: '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.3 6.4-1.5 6.4-7A5.4 5.4 0 0 0 20 4.8 5 5 0 0 0 19.9 1S18.7.7 16 2.5a13.4 13.4 0 0 0-7 0C6.3.7 5.1 1 5.1 1A5 5 0 0 0 5 4.8a5.4 5.4 0 0 0-1.5 3.8c0 5.4 3.3 6.6 6.4 7a3.4 3.4 0 0 0-.9 2.6V22"/>',
  };

  function icon(name, cls) {
    return '<svg class="' + (cls || "ic") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (ICONS[name] || "") + "</svg>";
  }

  function mountIcons(root) {
    (root || document).querySelectorAll("[data-icon]").forEach(function (el) {
      el.innerHTML = icon(el.dataset.icon, el.classList.contains("ic-sm") ? "ic-sm" : "ic");
    });
  }

  function reveal() {
    const els = document.querySelectorAll("[data-reveal]");
    if (REDUCED || !("IntersectionObserver" in window)) { els.forEach(function (e) { e.classList.add("in"); }); return; }
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.15 });
    els.forEach(function (e) { io.observe(e); });
  }

  // Painted repair: a brush stroke is drawn through the struck word; the CSS
  // then lets the corrected word fade in once .in is set.
  function paintRepair(el) {
    const s = el.querySelector("s");
    if (!s) { el.classList.add("in"); return Promise.resolve(); }
    let svg = s.querySelector("svg.stroke");
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "stroke");
      svg.setAttribute("viewBox", "0 0 100 10");
      svg.setAttribute("preserveAspectRatio", "none");
      svg.setAttribute("aria-hidden", "true");
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", "M1 6 Q 25 3, 50 6 T 99 5");      // a slightly wobbly hand stroke
      svg.appendChild(p);
      s.appendChild(svg);
    }
    const path = svg.querySelector("path");
    el.classList.add("in");
    if (REDUCED) { path.style.strokeDasharray = ""; path.style.strokeDashoffset = "0"; return Promise.resolve(); }
    const len = 120;
    path.style.strokeDasharray = String(len);
    path.style.strokeDashoffset = String(len);
    const anim = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return anim.finished.catch(function () {});
  }

  // A rubber stamp landing: big and faint, then down with a short dip at contact.
  function stamp(el) {
    el.style.opacity = "";
    if (REDUCED) return Promise.resolve();
    const a = el.animate([
      { transform: "rotate(-3deg) scale(1.35)", opacity: 0 },
      { opacity: 1, offset: 0.6 },
      { opacity: 0.8, offset: 0.7 },
      { transform: "rotate(-3deg) scale(1)", opacity: 1 },
    ], { duration: 400, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    return a.finished.catch(function () {});
  }

  function typingDots() {
    const d = document.createElement("div");
    d.className = "typing";
    d.setAttribute("aria-hidden", "true");
    d.innerHTML = "<i></i><i></i><i></i>";
    return d;
  }

  function timer(el) {
    let t0 = 0, id = null;
    function tick() {
      const s = Math.floor((Date.now() - t0) / 1000);
      el.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }
    return {
      start: function () { t0 = Date.now(); tick(); clearInterval(id); id = setInterval(tick, 1000); },
      stop: function () { clearInterval(id); id = null; },
      reset: function () { this.stop(); el.textContent = "00:00"; },
    };
  }

  // Twelve bars. With an AnalyserNode they follow the mic; without one they
  // idle at a gentle pattern while live and rest flat otherwise.
  function waveform(container, bars) {
    container.innerHTML = "";
    const n = bars || 12, els = [];
    for (let i = 0; i < n; i++) { const b = document.createElement("i"); container.appendChild(b); els.push(b); }
    let analyser = null, buf = null, live = false, phase = 0, raf = null;
    function frame() {
      if (analyser) {
        analyser.getByteTimeDomainData(buf);
        const step = Math.floor(buf.length / n);
        for (let i = 0; i < n; i++) {
          let peak = 0;
          for (let j = i * step; j < (i + 1) * step; j++) peak = Math.max(peak, Math.abs(buf[j] - 128));
          els[i].style.height = Math.max(4, Math.min(28, peak / 128 * 60)) + "px";
        }
      } else if (live && !REDUCED) {
        phase += 0.18;
        for (let i = 0; i < n; i++) els[i].style.height = (8 + 10 * Math.abs(Math.sin(phase + i * 0.6))) + "px";
      } else {
        for (let i = 0; i < n; i++) els[i].style.height = "4px";
      }
      raf = requestAnimationFrame(frame);
    }
    frame();
    return {
      attach: function (a) { analyser = a; buf = new Uint8Array(a.fftSize); },
      detach: function () { analyser = null; },
      setLive: function (v) { live = !!v; },
      stop: function () { cancelAnimationFrame(raf); },
    };
  }

  let statusCache = null;
  function status() {
    if (!statusCache) {
      statusCache = fetch("api/status").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }
    return statusCache;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function repairNode(c) {
    const el = document.createElement("span");
    el.className = "repair";
    el.innerHTML = '<s aria-label="suna: ' + esc(c.from_token) + '">' + esc(c.from_token) + "</s>" +
      '<b aria-label="padha: ' + esc(c.to_surface) + '">' + esc(c.to_surface) + "</b>" +
      (c.asr_confidence != null ? "<small>" + Number(c.asr_confidence).toFixed(2) + "</small>" : "");
    return el;
  }

  global.Signboard = { REDUCED: REDUCED, icon: icon, mountIcons: mountIcons, reveal: reveal,
    paintRepair: paintRepair, stamp: stamp, typingDots: typingDots, timer: timer,
    waveform: waveform, status: status, esc: esc, repairNode: repairNode };

  document.addEventListener("DOMContentLoaded", function () { mountIcons(); reveal(); });
})(window);
