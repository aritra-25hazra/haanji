# HaanJi transparency log

One JSON line per sealed day per tenant: the Merkle root over that day's receipts and its Ed25519 signature. Appended by a scheduled workflow; verify any line against `/api/receipts/export` as described at `/transparency` on the engine.
