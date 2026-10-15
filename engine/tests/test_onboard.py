"""Onboarding: five answers become a pack that books and answers."""
import asyncio
import datetime as dt
import sqlite3

import pytest
from fastapi.testclient import TestClient

from haanji import onboard, server
from haanji.pipeline import run_scenario
from haanji.pramaan.ledger import Ledger
from haanji.scenario import scenarios_of
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import from_dict

ANSWERS = {
    "business_name": "Sharma Physio Centre", "business_type": "clinic", "staff": ["Dr Sharma", "Priya"],
    "hours": {"mon-sat": ["09:00", "19:00"], "sun": None},
    "services": [{"name": "Physiotherapy session", "duration_min": 45, "price_inr": 800, "staff": ["Dr Sharma"], "aliases": ["physio"]},
                 {"name": "back pain consult", "duration_min": 30, "price_inr": 500}],
    "places": ["Vijay Nagar"],
}


def test_a_draft_is_a_complete_valid_pack():
    text, problems, data = onboard.draft(ANSWERS)
    assert problems == [] and data["pack"] == "sharma_physio_centre"
    pack = from_dict(data)
    assert pack.persona.business_name == "Sharma Physio Centre" and pack.staff_role == "doctor"
    assert [s.name for s in pack.services] == ["physiotherapy session", "back pain consult"]
    assert pack.services[1].staff == ["Dr Sharma", "Priya"], "a service with no staff named gets everyone"
    assert pack.hours and 6 not in pack.hours and pack.places == ["Vijay Nagar"]
    assert any("timings" in k[0] for k in pack.knowledge) and any("charge" in k[0] for k in pack.knowledge)
    assert [sc.name for sc in pack.scenarios] == ["booking", "price_faq"]
    assert text.startswith("# Vertical Pack") and "refuse:" in text


def test_the_generated_scenarios_pass_on_the_generated_pack():
    _, _, data = onboard.draft(ANSWERS)
    pack = from_dict(data)
    from haanji.clock import set_speed
    set_speed(200.0)

    async def go():
        outcomes = {}
        for sc in scenarios_of(pack):
            backend, _ = open_backend(pack, "t_onboard", today=dt.date(2026, 9, 7))
            ledger = Ledger(sqlite3.connect(":memory:"))
            registry = build_registry("t_onboard", backend, pack, ledger)
            _, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry, ledger=ledger, tenant_id="t_onboard")
            outcomes[sc.name] = report.outcome.value
        return outcomes
    assert asyncio.run(go()) == {"booking": "BOOKED", "price_faq": "FAQ_ANSWERED"}


def test_the_booking_scenario_avoids_a_closed_tomorrow():
    _, _, data = onboard.draft({**ANSWERS, "hours": {"wed-sun": ["10:00", "20:00"], "mon": None, "tue": None}})
    assert data["scenarios"][0]["turns"][1]["truth"].startswith("parso")


def test_the_draft_endpoint_reports_problems_and_never_saves(tmp_path):
    client = TestClient(server.app)
    r = client.post("/api/packs/draft", json=ANSWERS)
    assert r.status_code == 200 and r.json()["problems"] == [] and r.json()["exists"] is False
    bad = client.post("/api/packs/draft", json={**ANSWERS, "staff": [], "services": []}).json()
    assert "pack defines no services" in bad["problems"] and "pack defines no staff" in bad["problems"]
    assert client.post("/api/packs/draft", json={"business_name": ""}).status_code == 422
    assert "sharma_physio_centre" not in client.get("/api/status").json()["packs"]


def test_slug():
    assert onboard.slug("Dr. Mehta's Dental & Implant Clinic") == "dr_mehta_s_dental_implant_clinic"
    assert onboard.slug("   ") == "my_business"
