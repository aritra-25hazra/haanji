/* Pramaan chain verification, client-side.
 *
 * Mirrors haanji/pramaan/receipt.py + verifier.py exactly:
 *   payload_hash = SHA-256( cjson(action_args) || cjson(confirmation) ||
 *                           transcript_excerpt || occurred_at ||
 *                           str(agent_config_version) || action )
 *   chain_hash   = SHA-256( prev_hash || payload_hash )
 *   signature    = Ed25519 over chain_hash, against the tenant public key.
 *
 * Nothing here trusts the export: every hash is recomputed from the stored
 * fields, and the canonical JSON is rebuilt from the parsed objects rather
 * than taken from the export's own strings.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.PramaanVerifier = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function canonicalJson(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
    const keys = Object.keys(value).sort();
    return "{" + keys.map(k => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") + "}";
  }

  const enc = new TextEncoder();
  const fromHex = h => new Uint8Array((h.match(/../g) || []).map(b => parseInt(b, 16)));
  const toHex = a => Array.from(a, b => b.toString(16).padStart(2, "0")).join("");
  const concat = (...parts) => {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  };

  async function sha256(bytes) {
    if (typeof crypto !== "undefined" && crypto.subtle) {
      return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    }
    // node fallback (used by the cross-language test)
    const { createHash } = require("crypto");
    return new Uint8Array(createHash("sha256").update(Buffer.from(bytes)).digest());
  }

  async function payloadHash(r) {
    const args = typeof r.action_args === "string" ? JSON.parse(r.action_args) : r.action_args;
    const conf = typeof r.confirmation === "string" ? JSON.parse(r.confirmation) : r.confirmation;
    return sha256(concat(
      enc.encode(canonicalJson(args)),
      enc.encode(canonicalJson(conf)),
      enc.encode(r.transcript_excerpt),
      enc.encode(r.occurred_at),
      enc.encode(String(r.agent_config_version)),
      enc.encode(r.action)));
  }

  async function verifyReceipt(r, publicKeyHex, nacl) {
    const p = await payloadHash(r);
    if (toHex(p) !== r.payload_hash) {
      return { ok: false, reason: "payload hash does not match the stored content" };
    }
    const chain = await sha256(concat(fromHex(r.prev_hash), p));
    if (toHex(chain) !== r.chain_hash) {
      return { ok: false, reason: "chain hash does not match prev_hash + payload_hash" };
    }
    const sigOk = nacl.sign.detached.verify(chain, fromHex(r.signature), fromHex(publicKeyHex));
    if (!sigOk) {
      return { ok: false, reason: "signature does not verify against the tenant public key" };
    }
    return { ok: true };
  }

  async function verifyChain(exportObj, nacl) {
    const receipts = [...(exportObj.receipts || [])].sort((a, b) => a.seq - b.seq);
    const report = { ok: true, checked: 0, total: receipts.length,
                     firstBrokenSeq: null, reason: null, missing: [], rows: [] };
    if (!receipts.length) return report;

    const present = new Set(receipts.map(r => r.seq));
    for (let s = receipts[0].seq; s <= receipts[receipts.length - 1].seq; s++) {
      if (!present.has(s)) report.missing.push(s);
    }
    let prev = receipts[0].seq === 1 ? "0".repeat(64) : receipts[0].prev_hash;
    for (const r of receipts) {
      let row = { seq: r.seq, action: r.action, code: r.chain_hash.slice(0, 8).toUpperCase(),
                  ok: true, reason: null };
      if (r.prev_hash !== prev) {
        row.ok = false; row.reason = "prev_hash does not match the previous receipt's chain hash";
      } else {
        const v = await verifyReceipt(r, exportObj.public_key, nacl);
        row.ok = v.ok; row.reason = v.reason || null;
      }
      report.rows.push(row);
      if (!row.ok && report.ok) {
        report.ok = false; report.firstBrokenSeq = r.seq; report.reason = row.reason;
      }
      if (!row.ok) { report.rows.push(...receipts.slice(report.rows.length).map(x => (
        { seq: x.seq, action: x.action, code: x.chain_hash.slice(0, 8).toUpperCase(),
          ok: null, reason: "not checked — the chain is already broken above" }))); break; }
      prev = r.chain_hash;
      report.checked += 1;
    }
    if (report.ok && report.missing.length) {
      report.ok = false;
      report.firstBrokenSeq = report.missing[0];
      report.reason = "sequence gap — a receipt was deleted";
    }
    return report;
  }

  return { canonicalJson, payloadHash, verifyReceipt, verifyChain, toHex, fromHex };
});
