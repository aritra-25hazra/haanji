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
