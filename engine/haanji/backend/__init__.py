"""The business system the agent acts on.

In production this is the tenant's own calendar — the Core API's booking
service, or a connector into Google Calendar, Practo or a salon POS. The
engine only ever sees this interface, so the same conversation code runs
against a real clinic and against the local SQLite backend used by the demo,
the tests and the benchmark.
"""
from .local import LocalBackend, Booking, Slot, BackendError

__all__ = ["LocalBackend", "Booking", "Slot", "BackendError"]
