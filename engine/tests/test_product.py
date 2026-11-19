"""Product mode: the server offers a multispeciality clinic and a coaching
institute (packs/product/), and on a demo server visitors book into a demo
twin of each, never into the shop itself. The research packs stay as they were."""
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import AuthStore
from haanji.vertical import PACK_DIR, list_packs as research_packs, load_pack

CLINIC, COACHING = "smile_care_clinic", "pragati_classes"
OWNER = "9800000001"
PRODUCT_DIR = os.path.join(PACK_DIR, "product")
ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    monkeypatch.setattr(server, "PRODUCT", True)
    monkeypatch.setattr(server, "PUBLIC_SIMULATOR", True)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    before = set(server._sessions)
    yield TestClient(server.app)
    # Calls left open would count against the engine's concurrent-call cap for
    # every later test in the run ("the desk is busy").
    for sid in set(server._sessions) - before:
        server._sessions.pop(sid, None)
    for key, sid in list(server._wa_sessions.items()):
        if sid not in server._sessions:
            server._wa_sessions.pop(key, None)


def owner(client):
    code = client.post("/api/auth/otp", json={"phone": OWNER}).json()["dev_code"]
    tok = client.post("/api/auth/verify", json={"phone": OWNER, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_the_product_packs_are_valid_and_kept_apart_from_the_research_corpus():
    assert CLINIC not in research_packs() and COACHING not in research_packs()
    clinic = load_pack(os.path.join(PRODUCT_DIR, f"{CLINIC}.yaml"))
    coaching = load_pack(os.path.join(PRODUCT_DIR, f"{COACHING}.yaml"))
    assert clinic.validate() == [] and coaching.validate() == []
    assert 10 <= len(clinic.staff) <= 15
    assert {d.name for d in clinic.departments} == {"Dental", "General Surgery", "General Physician",
                                                    "Paediatrics", "Orthopaedics", "Gynaecology"}
    assert {d.name for d in coaching.departments} == {"Class 10 Boards", "Class 11-12 Boards", "JEE", "NEET"}
    assert clinic.department_of("Dr Mehta").code == "GP"


@pytest.mark.parametrize("pack", [CLINIC, COACHING])
def test_every_product_scenario_reaches_its_outcome(pack):
    run = subprocess.run([sys.executable, "-m", "haanji.cli", "selftest", "--pack",
                          os.path.join(PRODUCT_DIR, f"{pack}.yaml"), "--speed", "200"],
                         cwd=ENGINE, capture_output=True, text=True, timeout=240)
    assert run.returncode == 0, run.stdout + run.stderr


def test_the_server_offers_only_the_product_and_its_demo_copies(client):
    st = client.get("/api/status").json()
    assert st["product"] is True
    assert set(st["packs"]) == {CLINIC, COACHING, CLINIC + "_demo", COACHING + "_demo"}
    assert set(st["public_demo_packs"]) == {CLINIC + "_demo", COACHING + "_demo"}
    assert "dental_clinic" not in st["packs"] and "salon_spa" not in st["packs"]


def test_a_visitor_books_into_the_demo_copy_and_the_shop_stays_clean(client):
    r = client.post("/api/sessions", json={"pack": CLINIC}).json()
    assert r["pack"] == CLINIC + "_demo" and r["business"].endswith("(Demo)")
    visitor = None                                   # the simulator page keeps the pass between messages
    for line in ["mujhe bukhar ke liye doctor dikhana hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                 "mera naam Ravi Kumar hai number 9876501234", "haan confirm kar do"]:
        visitor = client.post("/api/wa/incoming", json={"pack": CLINIC, "phone": "9811144401", "text": line,
                                                        "visitor": visitor}).json()["visitor"]
    demo = server.runtime(CLINIC + "_demo").backend.bookings(CLINIC + "_demo")
    assert any(b.service == "general consultation" for b in demo)
    assert server.runtime(CLINIC).backend.bookings(CLINIC) == []


def test_the_owner_signed_in_still_writes_to_the_shop(client):
    hdr = owner(client)
    for line in ["beti ke liye JEE ki demo class chahiye", "kal shaam ka time mil jayega", "haan theek hai",
                 "Sita Rao 9811144402", "haan confirm kar do"]:
        client.post("/api/wa/incoming", json={"pack": COACHING, "phone": "9811144402", "text": line}, headers=hdr)
    assert any(b.service == "jee demo class" for b in server.runtime(COACHING).backend.bookings(COACHING))
    assert server.runtime(COACHING + "_demo").backend.bookings(COACHING + "_demo") == []


def test_a_demo_copy_follows_its_shop_and_cannot_be_edited(client):
    hdr = owner(client)
    got = client.get(f"/api/packs/{CLINIC}_demo", headers=hdr).json()
    assert got["parsed"]["pack"] == CLINIC
    r = client.put(f"/api/packs/{CLINIC}_demo", json={"yaml": got["yaml"].replace(f"pack: {CLINIC}", f"pack: {CLINIC}_demo")},
                   headers=hdr)
    assert r.status_code == 409
