import datetime as dt
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The demo server keeps its calendars, ledgers and auth in HAANJI_VAR_DIR;
# every test session gets a fresh one so a booking made by one test cannot
# fill the slot another expects. Set before haanji.server is first imported.
os.environ.setdefault("HAANJI_VAR_DIR", tempfile.mkdtemp(prefix="haanji-test-"))
os.environ.setdefault("HAANJI_SCHEDULER", "0")

from haanji.clock import set_speed                       # noqa: E402
from haanji.pramaan.ledger import Ledger                 # noqa: E402
from haanji.tools.builtin import build_registry, open_backend   # noqa: E402
from haanji.vertical import load_pack, list_packs        # noqa: E402

TODAY = dt.date(2026, 9, 7)          # a Monday
TENANT = "t_test"

set_speed(200.0)                     # the suite must not wait on simulated audio


@pytest.fixture(autouse=True)
def _no_relative_day_lands_on_sunday(request, monkeypatch):
    """The server tests book "aaj", "kal" and "parso" through the live clock,
    and the packs are closed on Sunday, so on a Friday, Saturday or Sunday
    some of those bookings became leads (17 tests failed one Saturday). On
    those days the server's today is the Thursday before, when all three are
    open. A test about the live date itself opts out with @pytest.mark.real_today."""
    if request.node.get_closest_marker("real_today"):
        return
    import haanji.backend.local as local
    real = local.wall_today
    back = real().weekday() - 3                  # Fri 1, Sat 2, Sun 3
    if back > 0:
        monkeypatch.setattr(local, "wall_today", lambda: real() - dt.timedelta(days=back))


@pytest.fixture
def pack():
    return load_pack("dental_clinic")


@pytest.fixture(params=list_packs())
def any_pack(request):
    return load_pack(request.param)


@pytest.fixture
def ledger():
    return Ledger(sqlite3.connect(":memory:"))


@pytest.fixture
def backend(pack):
    be, _ = open_backend(pack, TENANT, today=TODAY)
    return be


@pytest.fixture
def registry(pack, backend, ledger):
    return build_registry(TENANT, backend, pack, ledger)
