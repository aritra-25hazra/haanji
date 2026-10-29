"""Per-pack settings the owner changes from the console.

Small, typed, with defaults, in its own SQLite file next to the rest of the
data. Nothing here is a secret; secrets stay in the environment. Unknown keys
are rejected so a typo in the console cannot silently become a setting."""
from __future__ import annotations
import json
import sqlite3
from typing import Any

DEFAULTS: dict[str, Any] = {
    "reminders_on": True,          # WhatsApp reminder the day before a booking
    "reminder_hour_ist": 18,       # when the day-before reminder goes out
    "reminder_day_before": True,   # False: same-day, two hours before
    "deposit_inr": 0,              # > 0: every new booking carries a payment link for this much
    "waitlist_on": True,           # a caller who found no slot is offered the next freed one
    "digest_hour_ist": 20,         # the owner's evening WhatsApp
    "language_script": "latin",    # latin | devanagari for the owner's own messages
}
TYPES: dict[str, type] = {k: type(v) for k, v in DEFAULTS.items()}
LIMITS = {"reminder_hour_ist": (0, 23), "digest_hour_ist": (0, 23), "deposit_inr": (0, 100000)}
CHOICES = {"language_script": ("latin", "devanagari")}


class SettingsError(ValueError):
    pass


class SettingsStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (tenant_id TEXT PRIMARY KEY, json TEXT NOT NULL)")
        self.conn.commit()

    def get(self, tenant_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT json FROM settings WHERE tenant_id=?", (tenant_id,)).fetchone()
        stored = json.loads(row[0]) if row else {}
        return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}

    def update(self, tenant_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get(tenant_id)
        for key, value in changes.items():
            if key not in DEFAULTS:
                raise SettingsError(f"unknown setting '{key}'")
            want = TYPES[key]
            if want is bool:
                if isinstance(value, str):
                    value = value.lower() in ("1", "true", "on", "yes")
                value = bool(value)
            elif want is int:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise SettingsError(f"'{key}' must be a whole number")
                lo, hi = LIMITS.get(key, (None, None))
                if lo is not None and not (lo <= value <= hi):
                    raise SettingsError(f"'{key}' must be between {lo} and {hi}")
            else:
                value = str(value)
                if key in CHOICES and value not in CHOICES[key]:
                    raise SettingsError(f"'{key}' must be one of {', '.join(CHOICES[key])}")
            current[key] = value
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (tenant_id, json.dumps(current)))
        return current
