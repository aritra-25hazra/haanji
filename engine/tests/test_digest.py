"""The evening digest is the "Today" screen in a few lines: every number it
quotes is the dashboard's (insights.compute, India's day), under the
dashboard's names, in the owner's language."""
import re

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack

PACK = "dental_clinic"


@pytest.fixture
def client():
    server._buckets.clear()
    c = TestClient(server.app)
    c.post("/api/admin/demo-reset", params={"pack": PACK})          # a clean day
    yield c
    server.settings.update(PACK, {"owner_language": "hi"})


def book(client, phone):
    sc = next(s for s in scenarios_of(load_pack(PACK)) if s.name == "booking_with_asr_noise")
    for u in sc.utterances:
        client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": u.truth.replace("9876543210", phone)})


def test_every_number_in_the_digest_is_the_dashboard_s(client):
    book(client, "9811100021")
    book(client, "9811100022")
    client.post("/api/wa/incoming", json={"pack": PACK, "phone": "9811100023", "text": "mujhe insaan se baat karni hai"})
    ins = client.get("/api/insights", params={"pack": PACK}).json()
    text = client.get("/api/digest", params={"pack": PACK}).json()["text"]
    assert ins["calls_today"] >= 3 and ins["bookings_confirmed"] == 2 and ins["leads_open"] >= 1
    assert f"Aaj {ins['calls_today']} calls · {ins['bookings_confirmed']} booking hui (lagbhag ₹{ins['revenue_booked_inr']:,})." in text
    assert f"Callback chahiye: {ins['leads_open']}." in text
    assert ins["revenue_booked_inr"] > 0
    busiest = max(ins["by_hour"], key=lambda h: h["calls"])
    assert f"{busiest['hour']}:00 ({busiest['calls']} call" in text
    assert sum(ins["outcomes"].values()) == ins["calls_today"], "the outcome bar counts exactly today's calls"


def test_the_digest_speaks_the_owner_s_language(client):
    book(client, "9811100024")
    client.put("/api/settings", params={"pack": PACK}, json={"owner_language": "en"})
    text = client.get("/api/digest", params={"pack": PACK}).json()["text"]
    assert re.search(r"Today 1 call · 1 booked \(about ₹[\d,]+\)\.", text) and "Needs a callback:" in text
    assert "Aaj" not in text


def test_a_quiet_day_says_so(client):
    text = client.get("/api/digest", params={"pack": PACK}).json()["text"]
    assert "Aaj koi call nahi aayi." in text and "Callback chahiye: 0." in text
