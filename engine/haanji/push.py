"""Web push to the owner's phone: "nayi booking".

Standard Web Push (RFC 8030) with VAPID keys generated once beside the
database; the console registers a service worker, asks for permission and
posts its subscription here. Sending goes through ``pywebpush``; a failed
or expired subscription is dropped, never retried into a call.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import sqlite3
from typing import Any, Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
  endpoint  TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  sub_json  TEXT NOT NULL,
  label     TEXT NOT NULL DEFAULT '',
  created   TEXT NOT NULL
);
"""


def _vapid_keys(path: str) -> tuple[str, str]:
    """(private PEM, public key base64url) — generated once, kept with the data."""
    if os.path.exists(path):
        d = json.loads(open(path, encoding="utf-8").read())
        return d["private_pem"], d["public_key"]
    # A VAPID key is a P-256 ECDSA key; `cryptography` is already a hard
    # dependency, so the engine never needs the push library just to start.
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    public = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"private_pem": private_pem, "public_key": public}, fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return private_pem, public


class PushStore:
    def __init__(self, db_path: str, keys_path: str, sender: Callable[..., Any] | None = None,
                 contact: str = "mailto:owner@example.com"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.private_pem, self.public_key = _vapid_keys(keys_path)
        self.contact = contact
        self._sender = sender                       # tests inject one; production uses pywebpush

    def subscribe(self, tenant_id: str, subscription: dict[str, Any], label: str = "") -> int:
        endpoint = str(subscription.get("endpoint", ""))
        if not endpoint.startswith("https://"):
            raise ValueError("a push subscription needs an https endpoint")
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO push_subscriptions VALUES (?,?,?,?,?)",
                              (endpoint, tenant_id, json.dumps(subscription), label[:60],
                               dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return self.count(tenant_id)

    def unsubscribe(self, endpoint: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
        return cur.rowcount > 0

    def count(self, tenant_id: str) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM push_subscriptions WHERE tenant_id=?", (tenant_id,)).fetchone()["c"]

    def subscriptions(self, tenant_id: str) -> list[dict[str, Any]]:
        return [json.loads(r["sub_json"]) for r in self.conn.execute(
            "SELECT sub_json FROM push_subscriptions WHERE tenant_id=?", (tenant_id,))]

    def send(self, tenant_id: str, title: str, body: str, url: str = "/") -> dict[str, int]:
        """Push to every subscriber of the tenant; drop subscriptions that
        the push service says are gone (404/410)."""
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        sent = dropped = failed = 0
        for sub in self.subscriptions(tenant_id):
            try:
                if self._sender is not None:
                    self._sender(sub, payload)
                else:
                    from pywebpush import webpush
                    webpush(subscription_info=sub, data=payload, vapid_private_key=self.private_pem,
                            vapid_claims={"sub": self.contact}, ttl=3600, timeout=5)
                sent += 1
            except Exception as exc:                      # noqa: BLE001 - one bad phone must not stop the rest
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    self.unsubscribe(sub.get("endpoint", ""))
                    dropped += 1
                else:
                    failed += 1
        return {"sent": sent, "dropped": dropped, "failed": failed}
