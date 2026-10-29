/* HaanJi — the Talk page's 3D counter.

   The engine panel's three cards say in words what happened on a turn; this
   draws the same three things as objects on a painted shop counter, so a
   visitor can watch them happen:

     Bhasha       hanging sign plates. A misheard word is painted on the front;
                  the plate turns round and the word the shop actually sells is
                  on the back.
     Speculation  two lanes, the caller's sentence and the tool's answer. A hit
                  is a token that reaches the line before the caller does.
     Pramaan      receipt slabs, chained. A rubber stamp comes down on each new
                  one and leaves its code in sindoor ink.

   It is decoration over the cards, never instead of them: the canvas is
   aria-hidden, the cards stay the accessible record, and the page works the
   same without WebGL2, without this file, or with the 3D switched off.
   The talk page tells it what happened through "haanji:call" events.
   Plain ES module, no build; three.js is vendored next to it. */

const stage = document.getElementById("stage");
const canvas = document.getElementById("stage-canvas");
const toggle = document.getElementById("stage-toggle");
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const KEY = "haanji.3d";

let counter = null;
let enabled = false;
let booting = null;

function supported() {
  try { return !!document.createElement("canvas").getContext("webgl2"); } catch (e) { return false; }
}
function wanted() {
  try { return localStorage.getItem(KEY) !== "0"; } catch (e) { return true; }
}
function remember(on) {
  try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* private mode: not remembered */ }
}
function fontsReady() {
  if (!document.fonts || !document.fonts.load) return Promise.resolve();
  const faces = ['800 64px "Bricolage Grotesque"', '400 64px "Yatra One"', '500 48px "JetBrains Mono"', '600 40px "Instrument Sans"'];
  return Promise.race([
    Promise.all(faces.map((f) => document.fonts.load(f).catch(() => null))),
    new Promise((r) => setTimeout(r, 2500)),
  ]);
}

async function boot() {
  const THREE = await import("./three-0.170.0.module.min.js");
  await fontsReady();
  counter = buildCounter(THREE);
  if (window.HaanjiTalk) counter.restore(window.HaanjiTalk);
  stage.classList.add("ready");
}

async function setEnabled(on) {
  enabled = on;
  remember(on);
  toggle.setAttribute("aria-pressed", String(on));
  toggle.title = on ? "3D counter band karo" : "3D counter chalu karo";
  stage.classList.toggle("off", !on);
  if (!on) { if (counter) counter.pause(); return; }
  if (!counter) {
    booting = booting || boot();
    try { await booting; } catch (err) {
      console.warn("HaanJi 3D counter is off:", err);
      stage.hidden = true;
      return;
    }
  }
  if (enabled) counter.resume();
}

document.addEventListener("haanji:call", (e) => { if (counter && enabled) counter.handle(e.detail || {}); });

if (!stage || !canvas || !toggle || !supported()) {
  if (stage) stage.hidden = true;
} else {
  toggle.addEventListener("click", () => setEnabled(!enabled));
  setEnabled(wanted());
}

/* ─────────────────────────────────────────────────────────────── the scene */
function buildCounter(THREE) {
  const css = getComputedStyle(document.documentElement);
  const tok = (n) => css.getPropertyValue(n).trim();
  const HEX = {
    cobalt: tok("--cobalt"), deep: tok("--cobalt-deep"), marigold: tok("--marigold"), chalk: tok("--chalk"),
    ink: tok("--ink"), haze: tok("--haze"), sindoor: tok("--sindoor"), sindoorInk: tok("--sindoor-ink"),
    leaf: tok("--leaf"), leafInk: tok("--leaf-ink"),
  };
  const COL = {};
  for (const k of Object.keys(HEX)) COL[k] = new THREE.Color(HEX[k]);
  const FONT = { display: tok("--font-display"), dev: tok("--font-dev"), body: tok("--font-body"), mono: tok("--font-mono") };
  const rgba = (hex, a) => {
    const n = parseInt(hex.replace("#", ""), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  /* renderer, camera, light */
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const maxAniso = renderer.capabilities.getMaxAnisotropy();

  const scene = new THREE.Scene();
  scene.background = COL.deep.clone();
  scene.fog = new THREE.Fog(COL.deep, 14, 26);

  const camera = new THREE.PerspectiveCamera(28, 2, 0.1, 80);
  const camTarget = new THREE.Vector3(0.05, 1.32, -0.25);
  const camDir = new THREE.Vector3(0, 0.34, 1).normalize();
  const camBase = new THREE.Vector3();
  const camNow = new THREE.Vector3();

  scene.add(new THREE.HemisphereLight(COL.chalk, COL.deep, 1.15));
  const sun = new THREE.DirectionalLight(COL.chalk, 2.5);
  sun.position.set(-4.5, 8, 6.5);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -7, right: 7, top: 5, bottom: -5, near: 1, far: 26 });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  scene.add(sun);

  /* paint: three flat tones, the way a signwriter shades, and an ink outline */
  const grad = new THREE.DataTexture(new Uint8Array([120, 195, 255]), 3, 1, THREE.RedFormat);
  grad.minFilter = THREE.NearestFilter;
  grad.magFilter = THREE.NearestFilter;
  grad.generateMipmaps = false;
  grad.needsUpdate = true;
  const toon = (color, extra) => new THREE.MeshToonMaterial(Object.assign(
    { color: color instanceof THREE.Color ? color : new THREE.Color(color), gradientMap: grad }, extra || {}));
  const inkMat = new THREE.MeshBasicMaterial({ color: COL.ink, side: THREE.BackSide });
  const OUT = 0.022;

  function box(w, h, d, mats, outline = true) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mats);
    m.castShadow = true;
    m.receiveShadow = true;
    g.add(m);
    if (outline) g.add(new THREE.Mesh(new THREE.BoxGeometry(w + 2 * OUT, h + 2 * OUT, d + 2 * OUT), inkMat));
    g.userData.mesh = m;
    return g;
  }
  function cylinder(rTop, rBottom, h, mats, outline = true, seg = 40) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBottom, h, seg), mats);
    m.castShadow = true;
    m.receiveShadow = true;
    g.add(m);
    if (outline) g.add(new THREE.Mesh(new THREE.CylinderGeometry(rTop + OUT, rBottom + OUT, h + 2 * OUT, seg), inkMat));
    g.userData.mesh = m;
    return g;
  }
  function texture(wPx, hPx, draw) {
    const c = document.createElement("canvas");
    c.width = wPx;
    c.height = hPx;
    draw(c.getContext("2d"), wPx, hPx);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = maxAniso;
    return t;
  }
  function fitFont(g, text, weightFamily, startPx, maxW) {
    let px = startPx;
    for (; px > 12; px -= 2) {
      g.font = `${weightFamily.weight} ${px}px ${weightFamily.family}`;
      if (g.measureText(text).width <= maxW) break;
    }
    return px;
  }
  function dispose(obj) {
    obj.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
      for (const m of mats) {
        if (m === inkMat) continue;
        if (m.map) m.map.dispose();
        m.dispose();
      }
    });
  }

  /* motion: a few tweens, all of which finish at once when motion is reduced */
  const tweens = new Set();
  const ease = {
    out: (k) => 1 - Math.pow(1 - k, 3),
    in: (k) => k * k * k,
    inOut: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
    back: (k) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
    linear: (k) => k,
  };
  const lerp = (a, b, k) => a + (b - a) * k;
  function tween(dur, update, opts = {}) {
    return new Promise((resolve) => {
      tweens.add({ start: null, delay: REDUCED ? 0 : opts.delay || 0, dur: REDUCED ? 0 : dur,
        ease: opts.ease || ease.out, update, resolve });
      kick();
    });
  }
  const wait = (ms) => tween(ms, () => {});
  function stepTweens(now) {
    for (const t of [...tweens]) {
      if (t.start === null) t.start = now + t.delay;
      if (now < t.start) continue;
      const raw = t.dur ? Math.min(1, (now - t.start) / t.dur) : 1;
      t.update(t.ease(raw), raw);
      if (raw >= 1) { tweens.delete(t); t.resolve(); }
    }
  }

  /* ── the counter ─────────────────────────────────────────────────────── */
  const W = 9.4, H = 0.7, D = 3.5;
  const ST = { bhasha: -3.0, spec: 0.05, pramaan: 3.0 };
  const front = texture(2686, 200, (g, w, h) => {
    g.fillStyle = HEX.deep;
    g.fillRect(0, 0, w, h);
    // the signwriter's double rule, top and bottom
    g.fillStyle = HEX.marigold;
    g.fillRect(0, 10, w, 8); g.fillRect(0, 26, w, 3);
    g.fillRect(0, h - 29, w, 3); g.fillRect(0, h - 18, w, 8);
    g.textBaseline = "middle";
    for (const [en, hi, x] of [["Bhasha", "भाषा", ST.bhasha], ["Speculation", "अनुमान", ST.spec], ["Pramaan", "प्रमाण", ST.pramaan]]) {
      const cx = ((x + W / 2) / W) * w;
      g.font = `800 74px ${FONT.display}`;
      const ew = g.measureText(en).width;
      g.font = `400 62px ${FONT.dev}`;
      const hw = g.measureText(hi).width;
      const x0 = cx - (ew + 24 + hw) / 2;
      g.fillStyle = HEX.marigold;
      g.font = `800 74px ${FONT.display}`;
      g.fillText(en, x0, h / 2 + 2);
      g.fillStyle = HEX.chalk;
      g.font = `400 62px ${FONT.dev}`;
      g.fillText(hi, x0 + ew + 24, h / 2 + 6);
    }
  });
  const side = toon(COL.deep);
  const counterTop = toon(COL.cobalt);
  const counterFront = new THREE.MeshBasicMaterial({ map: front });   // painted lettering keeps its true colour
  const counterBox = box(W, H, D, [side, side, counterTop, side, counterFront, side]);
  counterBox.position.y = -H / 2;
  counterBox.userData.mesh.castShadow = false;
  scene.add(counterBox);

  /* ── the shop's own signboard, on the wall behind the counter ───────── */
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(30, 12), toon(COL.deep));
  wall.position.set(0, 4, -D / 2 - 0.55);
  wall.receiveShadow = true;
  scene.add(wall);
  const BOARD = { w: 4.6, h: 1.0 };
  function boardFace(name) {
    return texture(2208, 480, (g, w, h) => {
      g.fillStyle = HEX.cobalt; g.fillRect(0, 0, w, h);
      // the painted double rule a signwriter puts round a board
      g.strokeStyle = HEX.marigold; g.lineWidth = 16; g.strokeRect(26, 26, w - 52, h - 52);
      g.lineWidth = 5; g.strokeRect(58, 58, w - 116, h - 116);
      g.fillStyle = HEX.chalk; g.font = `400 96px ${FONT.dev}`; g.textBaseline = "middle"; g.textAlign = "right";
      g.fillText("हाँजी", w - 120, h / 2 + 14);
      const devW = g.measureText("हाँजी").width;
      fitFont(g, name, { weight: 800, family: FONT.display }, 196, w - devW - 330);
      g.fillStyle = HEX.marigold; g.textAlign = "left";
      g.fillText(name, 120, h / 2 + 8);
    });
  }
  const boardFront = toon(0xffffff, { map: boardFace("HaanJi") });
  const boardEdge = toon(COL.deep);
  const board = box(BOARD.w, BOARD.h, 0.12, [boardEdge, boardEdge, boardEdge, boardEdge, boardFront, boardEdge]);
  board.position.set(ST.spec, 3.0, -D / 2 - 0.25);
  scene.add(board);
  for (const x of [-BOARD.w / 2 + 0.4, BOARD.w / 2 - 0.4]) {
    const chain = cylinder(0.018, 0.018, 1.4, toon(COL.marigold), false, 8);
    chain.position.set(ST.spec + x, 3.0 + BOARD.h / 2 + 0.7, -D / 2 - 0.25);
    scene.add(chain);
  }
  let boardName = "HaanJi";
  function setBusiness(name) {
    if (!name || name === boardName) return;
    boardName = name;
    const old = boardFront.map;
    boardFront.map = boardFace(name);
    boardFront.needsUpdate = true;
    if (old) old.dispose();
    // a new board goes up: it swings once on its chains
    tween(900, (k, raw) => { board.rotation.x = Math.sin(raw * Math.PI * 3) * 0.08 * (1 - raw); }, { ease: ease.linear });
  }

  /* ── Bhasha: plates that turn round ──────────────────────────────────── */
  const bh = new THREE.Group();
  bh.position.set(ST.bhasha, 0, -0.1);
  scene.add(bh);
  const iron = toon(COL.marigold);
  for (const x of [-1.38, 1.38]) {
    const post = box(0.08, 2.62, 0.08, iron);
    post.position.set(x, 1.31, -0.22);
    bh.add(post);
  }
  const rail = box(2.92, 0.08, 0.08, iron);
  rail.position.set(0, 2.62, -0.22);
  bh.add(rail);

  const PLATE_H = 0.6, PLATE_D = 0.08, PX = 380;
  const SLOT_Y = [2.06, 1.38, 0.7];
  let plates = [];
  let idlePlate = null;

  function plateWidth(text, alt) {
    const g = document.createElement("canvas").getContext("2d");
    g.font = `800 96px ${FONT.display}`;
    const tw = Math.max(g.measureText(text).width, alt ? g.measureText(alt).width : 0);
    return Math.max(1.3, Math.min(2.6, (tw * (PLATE_H / 0.44)) / PX + 0.45));
  }
  function plateFace(wWorld, paint) {
    return texture(Math.round(wWorld * PX), Math.round(PLATE_H * PX), paint);
  }
  function hookPair(group, w) {
    // two short hooks from the rail: the plate hangs like a shop sign
    for (const x of [-w / 2 + 0.18, w / 2 - 0.18]) {
      const hook = box(0.025, 0.12, 0.025, iron, false);
      hook.position.set(x, PLATE_H / 2 + 0.06, -0.02);
      group.add(hook);
    }
  }
  function makePlate(c) {
    const w = plateWidth(c.from_token, c.to_surface);
    const heard = plateFace(w, (g, pw, ph) => {
      g.fillStyle = HEX.chalk; g.fillRect(0, 0, pw, ph);
      g.strokeStyle = HEX.marigold; g.lineWidth = 6; g.strokeRect(12, 12, pw - 24, ph - 24);
      const px = fitFont(g, c.from_token, { weight: 800, family: FONT.display }, 120, pw - 120);
      g.fillStyle = rgba(HEX.cobalt, 0.55); g.textBaseline = "middle"; g.textAlign = "center";
      g.fillText(c.from_token, pw / 2, ph / 2 + 4);
      const tw = g.measureText(c.from_token).width;
      // the brush stroke through the misheard word
      g.strokeStyle = HEX.marigold; g.lineWidth = Math.max(8, px * 0.12); g.lineCap = "round";
      g.beginPath();
      g.moveTo(pw / 2 - tw / 2 - 10, ph / 2 + 10);
      g.quadraticCurveTo(pw / 2, ph / 2 - 4, pw / 2 + tw / 2 + 10, ph / 2 + 6);
      g.stroke();
      if (c.asr_confidence != null) {
        g.font = `500 34px ${FONT.mono}`; g.textAlign = "right"; g.fillStyle = rgba(HEX.cobalt, 0.75);
        g.fillText(Number(c.asr_confidence).toFixed(2), pw - 30, ph - 34);
      }
    });
    const read = plateFace(w, (g, pw, ph) => {
      g.fillStyle = HEX.marigold; g.fillRect(0, 0, pw, ph);
      g.strokeStyle = HEX.cobalt; g.lineWidth = 6; g.strokeRect(12, 12, pw - 24, ph - 24);
      fitFont(g, c.to_surface, { weight: 800, family: FONT.display }, 120, pw - 100);
      g.fillStyle = HEX.cobalt; g.textBaseline = "middle"; g.textAlign = "center";
      g.fillText(c.to_surface, pw / 2, ph / 2 + 4);
    });
    const edge = toon(COL.marigold);
    const plate = box(w, PLATE_H, PLATE_D, [edge, edge, edge, edge, toon(0xffffff, { map: heard }), toon(0xffffff, { map: read })]);
    hookPair(plate, w);
    return plate;
  }
  function makeIdlePlate() {
    const w = 1.8;
    const face = plateFace(w, (g, pw, ph) => {
      g.fillStyle = HEX.marigold; g.fillRect(0, 0, pw, ph);
      g.strokeStyle = HEX.cobalt; g.lineWidth = 6; g.strokeRect(12, 12, pw - 24, ph - 24);
      g.font = `400 140px ${FONT.dev}`; g.fillStyle = HEX.cobalt; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText("हाँजी", pw / 2, ph / 2 + 12);
    });
    const edge = toon(COL.marigold);
    const plate = box(w, PLATE_H, PLATE_D, [edge, edge, edge, edge, toon(0xffffff, { map: face }), edge]);
    hookPair(plate, w);
    plate.position.set(0, SLOT_Y[0], 0);
    return plate;
  }
  function showIdle(on) {
    if (on && !idlePlate) {
      idlePlate = makeIdlePlate();
      bh.add(idlePlate);
      idlePlate.scale.setScalar(0.001);
      tween(260, (k) => idlePlate && idlePlate.scale.setScalar(Math.max(0.001, k)), { ease: ease.back });
    } else if (!on && idlePlate) {
      const p = idlePlate;
      idlePlate = null;
      tween(160, (k) => p.scale.setScalar(Math.max(0.001, 1 - k)), { ease: ease.in }).then(() => { bh.remove(p); dispose(p); });
    }
  }
  function addRepair(c, animate) {
    showIdle(false);
    // everyone moves down a slot; the oldest beyond three is taken off its hooks
    plates.forEach((p, i) => {
      const from = p.position.y, to = SLOT_Y[i + 1];
      if (to === undefined) {
        tween(220, (k) => { p.scale.setScalar(Math.max(0.001, 1 - k)); p.position.y = from - k * 0.3; }, { ease: ease.in })
          .then(() => { bh.remove(p); dispose(p); });
      } else if (animate) {
        tween(300, (k) => { p.position.y = lerp(from, to, k); }, { ease: ease.inOut });
      } else {
        p.position.y = to;
      }
    });
    plates = plates.slice(0, 2);
    const plate = makePlate(c);
    plate.position.set(0, SLOT_Y[0], 0);
    bh.add(plate);
    plates.unshift(plate);
    if (!animate) { plate.rotation.y = Math.PI; return Promise.resolve(); }
    plate.scale.setScalar(0.001);
    return tween(260, (k) => plate.scale.setScalar(Math.max(0.001, k)), { ease: ease.back })
      .then(() => wait(380))
      .then(() => tween(620, (k) => {
        plate.rotation.y = k * Math.PI;
        plate.position.z = Math.sin(k * Math.PI) * 0.18;      // swings out from the rail as it turns
      }, { ease: ease.inOut }));
  }

  /* ── Speculation: the caller's sentence against the tool's answer ────── */
  const sp = new THREE.Group();
  sp.position.set(ST.spec, 0, 0);
  scene.add(sp);
  const LANE_L = 3.2, LANE_D = 0.56;
  const X0 = -LANE_L / 2, START = X0 + 0.95, FINISH = 0.72;
  const Z_CALLER = -0.52, Z_TOOL = 0.5;
  const laneTopMat = toon(0xffffff, { map: texture(1200, 224, (g, w, h) => {
    g.fillStyle = HEX.deep; g.fillRect(0, 0, w, h);
    g.strokeStyle = rgba(HEX.marigold, 0.4); g.lineWidth = 5; g.setLineDash([20, 16]);
    g.beginPath(); g.moveTo(330, h / 2); g.lineTo(w - 20, h / 2); g.stroke();
  }) });
  const lineMat = toon(COL.marigold);
  function laneHead(label) {
    // a small painted board standing at the start of the lane: what runs here
    const face = texture(370, 160, (g, w, h) => {
      g.fillStyle = HEX.chalk; g.fillRect(0, 0, w, h);
      g.strokeStyle = HEX.marigold; g.lineWidth = 9; g.strokeRect(6, 6, w - 12, h - 12);
      fitFont(g, label, { weight: 800, family: FONT.display }, 108, w - 44);
      g.fillStyle = HEX.cobalt; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(label, w / 2, h / 2 + 6);
    });
    return box(0.8, 0.35, 0.05, [lineMat, lineMat, lineMat, lineMat, toon(0xffffff, { map: face }), lineMat]);
  }
  for (const [z, label] of [[Z_CALLER, "caller"], [Z_TOOL, "jawab"]]) {
    const lane = box(LANE_L, 0.06, LANE_D, [side, side, laneTopMat, side, side, side]);
    lane.position.set(0, 0.03, z);
    sp.add(lane);
    const head = laneHead(label);
    head.position.set(X0 + 0.44, 0.24, z);
    sp.add(head);
  }
  const finishLine = box(0.06, 0.08, 1.95, lineMat, false);
  finishLine.position.set(FINISH, 0.04, -0.01);
  sp.add(finishLine);
  const flagPost = cylinder(0.035, 0.035, 1.12, lineMat);
  flagPost.position.set(FINISH, 0.56, Z_CALLER - 0.36);
  sp.add(flagPost);
  const flagTex = texture(400, 200, (g, w, h) => {
    g.fillStyle = HEX.marigold; g.fillRect(0, 0, w, h);
    fitFont(g, "sawaal", { weight: 800, family: FONT.display }, 112, w - 40);
    g.fillStyle = HEX.cobalt; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText("sawaal", w / 2, h / 2 + 6);
  });
  const flag = box(0.84, 0.42, 0.03, [lineMat, lineMat, lineMat, lineMat, toon(0xffffff, { map: flagTex }), lineMat]);
  flag.position.set(FINISH + 0.44, 0.88, Z_CALLER - 0.36);
  sp.add(flag);

  const barGeo = new THREE.BoxGeometry(1, 0.08, 0.3);
  barGeo.translate(0.5, 0, 0);                               // grows from its left end
  const callerBar = new THREE.Mesh(barGeo, toon(COL.chalk));
  callerBar.castShadow = true;
  callerBar.position.set(START, 0.1, Z_CALLER);
  callerBar.scale.x = 0.001;
  sp.add(callerBar);
  let callerLen = 0, turnOpen = false;
  const FULL = FINISH - START;
  function setCallerLen(len, dur) {
    const from = callerLen, to = Math.max(0.001, len);
    callerLen = to;
    return tween(dur, (k) => { callerBar.scale.x = lerp(from, to, k); }, { ease: ease.out });
  }

  const READ_TOOLS = { check_availability: "slot", search_knowledge: "FAQ", quote_price: "₹", lookup_customer: "ID" };
  let discs = [];
  function makeDisc(tool, hit) {
    const label = READ_TOOLS[tool] || tool.slice(0, 4);
    const top = texture(256, 256, (g, w, h) => {
      g.fillStyle = hit ? HEX.leaf : HEX.haze; g.fillRect(0, 0, w, h);
      g.strokeStyle = HEX.cobalt; g.lineWidth = 8;
      g.beginPath(); g.arc(w / 2, h / 2, w / 2 - 22, 0, Math.PI * 2); g.stroke();
      fitFont(g, label, { weight: 800, family: FONT.display }, 92, w - 80);
      g.fillStyle = HEX.cobalt; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(label, w / 2, h / 2 + 6);
    });
    const rim = toon(hit ? COL.leaf : COL.haze);
    const topMat = toon(0xffffff, { map: top, emissive: COL.leaf, emissiveIntensity: 0 });
    const d = cylinder(0.25, 0.25, 0.11, [rim, topMat, rim]);
    d.rotation.y = -Math.PI / 2;                               // the label reads from the front
    d.userData.top = topMat;
    return d;
  }
  function clearDiscs() {
    const old = discs;
    discs = [];
    for (const d of old) {
      tween(160, (k) => d.scale.setScalar(Math.max(0.001, 1 - k)), { ease: ease.in }).then(() => { sp.remove(d); dispose(d); });
    }
  }
  function beginTurn() {
    if (turnOpen) return;
    turnOpen = true;
    clearDiscs();
    setCallerLen(0.001, 160);
  }
  function race(t, animate) {
    turnOpen = false;
    const hits = new Set(t.speculation_hits || []);
    const tools = (t.tools || []).filter((x) => x in READ_TOOLS);
    const BAR = 760;
    if (!animate) callerBar.scale.x = callerLen = FULL;
    else setCallerLen(FULL, BAR);
    tools.slice(0, 2).forEach((tool, i) => {
      const hit = hits.has(tool);
      const d = makeDisc(tool, hit);
      const y = 0.115;
      discs.push(d);
      sp.add(d);
      if (hit) {
        // ready before the caller finished: it parks short of the line, then
        // hops when the sentence arrives and finds its answer waiting
        const park = FINISH - 0.36 - i * 0.56;
        if (!animate) { d.position.set(park, y, Z_TOOL); return; }
        d.position.set(START, y, Z_TOOL);
        d.scale.setScalar(0.001);
        tween(200, (k) => d.scale.setScalar(Math.max(0.001, k)), { ease: ease.back });
        tween(460, (k) => { d.position.x = lerp(START, park, k); }, { ease: ease.out });
        tween(420, (k, raw) => {
          d.position.y = y + Math.sin(raw * Math.PI) * 0.42;
          d.userData.top.emissiveIntensity = Math.sin(raw * Math.PI) * 0.5;
        }, { delay: BAR, ease: ease.linear });
      } else {
        // asked for first, computed after: it only sets off once the caller is done
        const park = FINISH + 0.34 + i * 0.52;
        if (!animate) { d.position.set(park, y, Z_TOOL); return; }
        d.position.set(START, y, Z_TOOL);
        d.scale.setScalar(0.001);
        tween(200, (k) => d.scale.setScalar(Math.max(0.001, k)), { delay: BAR, ease: ease.back });
        tween(620, (k) => { d.position.x = lerp(START, park, k); }, { delay: BAR, ease: ease.inOut });
      }
    });
  }

  /* ── Pramaan: stamped slabs, chained ─────────────────────────────────── */
  const pr = new THREE.Group();
  pr.position.set(ST.pramaan, 0, 0);
  scene.add(pr);
  const SLAB = { w: 1.32, h: 0.15, d: 0.84 };
  const P0 = new THREE.Vector3(-0.38, SLAB.h / 2, 0.78);
  const STEP = new THREE.Vector3(0.42, 0, -1.05);             // a gap the chain link sits in
  const posOf = (i) => P0.clone().addScaledVector(STEP, i);
  const MAX_SLABS = 3;
  let slabs = [];
  let links = [];
  let seq = 0;

  function slabTop(code, n, stamped) {
    return texture(976, 640, (g, w, h) => {
      g.fillStyle = HEX.chalk; g.fillRect(0, 0, w, h);
      g.fillStyle = rgba(HEX.cobalt, 0.1);
      for (let y = 210; y < h - 70; y += 62) g.fillRect(48, y, w - 96, 4);   // the printed slip's rules
      g.fillStyle = rgba(HEX.cobalt, 0.75); g.font = `600 40px ${FONT.body}`; g.textBaseline = "alphabetic";
      g.fillText("RECEIPT", 48, 90);
      g.font = `500 36px ${FONT.mono}`; g.textAlign = "right";
      g.fillText("seq " + n, w - 48, 90);
      g.textAlign = "left"; g.fillStyle = HEX.cobalt; g.font = `500 84px ${FONT.mono}`;
      g.fillText(code, 48, 180);
      if (!stamped) return;
      // the rubber stamp: sindoor ink, a little crooked, a little uneven
      g.save();
      g.translate(w * 0.6, h * 0.62);
      g.rotate(-0.1);
      g.strokeStyle = HEX.sindoorInk; g.fillStyle = HEX.sindoorInk; g.lineWidth = 12;
      const sw = 470, sh = 210;
      g.beginPath();
      if (g.roundRect) g.roundRect(-sw / 2, -sh / 2, sw, sh, 22); else g.rect(-sw / 2, -sh / 2, sw, sh);
      g.stroke();
      g.font = `800 92px ${FONT.display}`; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText("PRAMAAN", 0, -18);
      g.font = `500 38px ${FONT.mono}`;
      g.fillText("sealed · " + code, 0, 58);
      g.globalCompositeOperation = "destination-out";       // ink that did not quite take
      for (let i = 0; i < 160; i++) {
        g.globalAlpha = 0.25 + ((i * 37) % 50) / 100;
        g.beginPath();
        g.arc(((i * 97) % sw) - sw / 2, ((i * 61) % sh) - sh / 2, 2 + (i % 4), 0, Math.PI * 2);
        g.fill();
      }
      g.restore();
    });
  }
  function makeSlab(code, n) {
    const paper = toon(COL.chalk);
    const top = toon(0xffffff, { map: slabTop(code, n, false) });
    const s = box(SLAB.w, SLAB.h, SLAB.d, [paper, paper, top, paper, paper, paper]);
    s.userData.top = top;
    s.userData.code = code;
    s.userData.n = n;
    return s;
  }
  function stampSlab(s) {
    const old = s.userData.top.map;
    s.userData.top.map = slabTop(s.userData.code, s.userData.n, true);
    s.userData.top.needsUpdate = true;
    if (old) old.dispose();
  }

  const linkMat = toon(COL.marigold);
  function makeLink() {
    const g = new THREE.Group();
    const geo = new THREE.TorusGeometry(0.15, 0.042, 10, 28);
    const a = new THREE.Mesh(geo, linkMat);
    a.rotation.x = Math.PI / 2;
    a.castShadow = true;
    const b = new THREE.Mesh(geo, linkMat);
    b.castShadow = true;
    g.add(a, b);
    g.userData.a = a;
    g.userData.b = b;
    return g;
  }
  const dir = new THREE.Vector3();
  function placeLinks() {
    for (let i = 0; i < links.length; i++) {
      const s1 = slabs[i], s2 = slabs[i + 1];
      const L = links[i];
      if (!s1 || !s2) { L.visible = false; continue; }
      L.visible = true;
      dir.subVectors(s2.position, s1.position).setY(0).normalize();
      L.position.lerpVectors(s1.position, s2.position, 0.5).setY(0.16);
      L.userData.a.position.copy(dir).multiplyScalar(-0.12);
      L.userData.b.position.copy(dir).multiplyScalar(0.12);
      L.userData.b.rotation.set(0, -Math.atan2(dir.z, dir.x), 0);
      const fade = Math.min(s1.scale.x, s2.scale.x);
      L.scale.setScalar(Math.max(0.001, fade));
    }
  }

  const ghost = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(SLAB.w, SLAB.h, SLAB.d)),
    new THREE.LineDashedMaterial({ color: COL.marigold, dashSize: 0.08, gapSize: 0.06, transparent: true, opacity: 0.75 }));
  ghost.computeLineDistances();
  ghost.position.copy(P0);
  pr.add(ghost);

  // the stamp: a painted wooden handle, a cobalt block, a sindoor rubber face
  const stamp = new THREE.Group();
  const wood = toon(COL.marigold);
  const block = toon(COL.deep);
  const rubber = toon(COL.sindoor);
  const stampBase = box(0.74, 0.16, 0.54, [block, block, block, rubber, block, block]);
  stampBase.position.y = 0.08;
  const stampHandle = cylinder(0.09, 0.115, 0.5, wood);
  stampHandle.position.y = 0.41;
  const knob = new THREE.Mesh(new THREE.SphereGeometry(0.19, 28, 18), toon(COL.sindoor));
  knob.position.y = 0.75;
  knob.castShadow = true;
  const knobOut = new THREE.Mesh(new THREE.SphereGeometry(0.19 + OUT, 28, 18), inkMat);
  knobOut.position.y = 0.75;
  stamp.add(stampBase, stampHandle, knob, knobOut);
  const REST = new THREE.Vector3(1.12, 0, 1.18);
  stamp.position.copy(REST);
  pr.add(stamp);

  const splatMat = new THREE.MeshBasicMaterial({ color: COL.sindoor, transparent: true, opacity: 0, depthWrite: false });
  const splat = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.5, 48), splatMat);
  splat.rotation.x = -Math.PI / 2;
  pr.add(splat);

  async function press(s) {
    const above = new THREE.Vector3(s.position.x, 1.5, s.position.z);
    const from = stamp.position.clone();
    await tween(320, (k) => {
      stamp.position.lerpVectors(from, above, k);
      stamp.position.y = lerp(from.y, above.y, Math.sin(k * Math.PI / 2));
    }, { ease: ease.inOut });
    await tween(150, (k) => { stamp.position.y = lerp(1.5, SLAB.h, k); }, { ease: ease.in });
    stampSlab(s);
    splat.position.set(s.position.x, SLAB.h + 0.005, s.position.z);
    tween(520, (k) => { splat.scale.setScalar(1 + k * 1.1); splatMat.opacity = 0.55 * (1 - k); }, { ease: ease.out });
    await tween(150, (k, raw) => { stamp.scale.y = 1 - Math.sin(raw * Math.PI) * 0.14; }, { ease: ease.linear });
    const down = stamp.position.clone();
    await tween(380, (k) => {
      stamp.position.lerpVectors(down, REST, k);
      stamp.position.y = Math.sin(k * Math.PI) * 0.9 + lerp(down.y, REST.y, k);
    }, { ease: ease.inOut });
  }

  let chainBusy = Promise.resolve();
  function addReceipt(code, animate) {
    chainBusy = chainBusy.then(() => addReceiptNow(code, animate)).catch(() => {});
    return chainBusy;
  }
  async function addReceiptNow(code, animate) {
    seq += 1;
    ghost.visible = false;
    const s = makeSlab(code, seq);
    const starts = slabs.map((x) => x.position.clone());
    slabs.unshift(s);
    if (slabs.length > 1) { const L = makeLink(); links.unshift(L); pr.add(L); }
    pr.add(s);
    const target = slabs.map((_, i) => posOf(i));
    if (!animate) {
      slabs.forEach((x, i) => x.position.copy(target[i]));
      stampSlab(s);
    } else {
      s.position.copy(target[0]).setY(2.4);
      await Promise.all([
        tween(420, (k) => {
          for (let i = 1; i < slabs.length; i++) slabs[i].position.lerpVectors(starts[i - 1], target[i], k);
          placeLinks();
        }, { ease: ease.inOut }),
        tween(460, (k) => { s.position.y = lerp(2.4, target[0].y, k); placeLinks(); }, { ease: ease.back, delay: 80 }),
      ]);
      await press(s);
    }
    // the oldest leaves the counter
    while (slabs.length > MAX_SLABS) {
      const gone = slabs.pop();
      const L = links.pop();
      const p0 = gone.position.clone();
      tween(360, (k) => {
        gone.scale.setScalar(Math.max(0.001, 1 - k));
        gone.position.copy(p0).addScaledVector(STEP, k * 0.6);
        placeLinks();
      }, { ease: ease.in }).then(() => { pr.remove(gone); dispose(gone); if (L) { pr.remove(L); L.traverse((o) => o.geometry && o.geometry.dispose()); } });
    }
    placeLinks();
  }

  /* ── the loop ────────────────────────────────────────────────────────── */
  let raf = 0, paused = false, onScreen = true;
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  function kick() {
    if (!raf && !paused && onScreen && !document.hidden) raf = requestAnimationFrame(frame);
  }
  function frame(now) {
    raf = 0;
    stepTweens(now);
    pointer.x = lerp(pointer.x, pointer.tx, 0.07);
    pointer.y = lerp(pointer.y, pointer.ty, 0.07);
    const sway = REDUCED ? 0 : Math.sin(now / 4800) * 0.32;
    camNow.copy(camBase);
    camNow.x += sway + pointer.x * 0.9;
    camNow.y += pointer.y * 0.4;
    camera.position.copy(camNow);
    camera.lookAt(camTarget);
    renderer.render(scene, camera);
    const settling = Math.abs(pointer.x - pointer.tx) > 0.002 || Math.abs(pointer.y - pointer.ty) > 0.002;
    if (tweens.size || !REDUCED || settling) kick();
  }
  // The points that must stay in frame: the painted front of the counter, the
  // top of the signboard, the easel and the stamp. Near things project lower
  // than far ones, so the frame is found by projecting them, not by guessing.
  const KEEP = [
    [-W / 2, -H, D / 2], [W / 2, -H, D / 2], [-W / 2, 0, D / 2], [W / 2, 0, D / 2],
    [ST.spec - 2.4, 3.55, -D / 2 - 0.25], [ST.spec + 2.4, 3.55, -D / 2 - 0.25],
    [ST.bhasha - 1.45, 2.7, -0.3], [ST.pramaan + 1.55, 0.95, 1.2],
  ].map((a) => new THREE.Vector3(a[0], a[1], a[2]));
  const ndc = new THREE.Vector3();
  function bounds(dist) {
    camera.position.copy(camDir).multiplyScalar(dist).add(camTarget);
    camera.lookAt(camTarget);
    camera.updateMatrixWorld();
    let x = 0, yLo = Infinity, yHi = -Infinity;
    for (const v of KEEP) {
      ndc.copy(v).project(camera);
      x = Math.max(x, Math.abs(ndc.x));
      yLo = Math.min(yLo, ndc.y);
      yHi = Math.max(yHi, ndc.y);
    }
    return { x, yLo, yHi };
  }
  function fit() {
    const w = stage.clientWidth, h = canvas.clientHeight || stage.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    // centre the content vertically, then back off until it all fits
    for (let pass = 0; pass < 3; pass++) {
      let lo = 4, hi = 40;
      for (let i = 0; i < 24; i++) {
        const mid = (lo + hi) / 2, b = bounds(mid);
        if (b.x <= 0.94 && b.yHi <= 0.9 && b.yLo >= -0.96) hi = mid; else lo = mid;
      }
      const b = bounds(hi);
      const shift = ((b.yHi + b.yLo) / 2) * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * hi * 0.9;
      camTarget.y += shift;
      camBase.copy(camDir).multiplyScalar(hi).add(camTarget);
    }
    if (!raf) frame(performance.now());
  }
  new ResizeObserver(fit).observe(stage);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      onScreen = entries.some((e) => e.isIntersecting);
      kick();
    }).observe(stage);
  }
  document.addEventListener("visibilitychange", kick);
  if (!REDUCED) {
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      pointer.tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      pointer.ty = -((e.clientY - r.top) / r.height - 0.5) * 2;
      kick();
    });
    stage.addEventListener("pointerleave", () => { pointer.tx = 0; pointer.ty = 0; kick(); });
  }

  /* ── what the page tells it ─────────────────────────────────────────── */
  function reset() {
    for (const p of plates) { bh.remove(p); dispose(p); }
    plates = [];
    showIdle(true);
    for (const d of discs) { sp.remove(d); dispose(d); }
    discs = [];
    callerLen = 0.001;
    callerBar.scale.x = 0.001;
    turnOpen = false;
    for (const s of slabs) { pr.remove(s); dispose(s); }
    for (const L of links) { pr.remove(L); L.traverse((o) => o.geometry && o.geometry.dispose()); }
    slabs = [];
    links = [];
    seq = 0;
    ghost.visible = true;
    stamp.position.copy(REST);
    stamp.scale.set(1, 1, 1);
    kick();
  }
  function onTurn(t, animate = true) {
    const repairs = t.corrections || [];
    let chain = Promise.resolve();
    for (const c of repairs) chain = chain.then(() => addRepair(c, animate));
    race(t, animate);
    for (const code of t.receipts || []) addReceipt(code, animate);
  }

  fit();
  reset();

  return {
    handle(e) {
      if (e.type === "reset") { reset(); setBusiness(e.business); }
      else if (e.type === "partial") { beginTurn(); setCallerLen(Math.min(FULL * 0.86, 0.06 + String(e.text || "").length * 0.028), 140); }
      else if (e.type === "caller") { beginTurn(); setCallerLen(FULL * 0.9, 220); }
      else if (e.type === "turn" && e.turn) onTurn(e.turn, true);
      kick();
    },
    restore(state) {
      // a call already under way when the 3D arrived: draw it as it stands
      reset();
      const repairs = (state.repairs || []).slice(0, 3).reverse();
      if (repairs.length) { showIdle(false); for (const c of repairs) addRepair(c, false); }
      for (const code of state.receipts || []) addReceipt(code, false);
      kick();
    },
    pause() {
      paused = true;
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
    },
    resume() {
      paused = false;
      fit();
      kick();
    },
  };
}
