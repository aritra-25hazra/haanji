"""Bookings as a calendar: the iCalendar feed, one booking's file, and the Google push."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from haanji import calendar as cal
from haanji import server
from haanji.gcal import GoogleCalendar
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack


@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


def book(client, phone):
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    codes = []
    for u in sc.utterances:
        r = client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": phone, "text": u.truth}).json()
        codes += [c for rep in r["replies"] for c in rep.get("receipts", [])]
    return codes


def test_the_feed_is_valid_icalendar_with_the_tenant_s_bookings(client, monkeypatch):
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    codes = book(client, "9822200001")
    url = client.get("/api/calendar/feed-url", params={"pack": "dental_clinic"}).json()
    assert url["url"].startswith("https://haanji.example/api/calendar/dental_clinic.ics?token=") and url["webcal"].startswith("webcal://")
    token = url["url"].split("token=")[1]
    r = client.get("/api/calendar/dental_clinic.ics", params={"token": token})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and "TZID:Asia/Kolkata" in body and "END:VCALENDAR" in body
    assert "SUMMARY:root canal — Vijay Sharma" in body and f"Receipt: {codes[-1]}" in body.replace("\r\n ", "")
    assert "https://haanji.example/verify?code=" in body.replace("\r\n ", "")
    assert client.get("/api/calendar/dental_clinic.ics", params={"token": "nope"}).status_code == 403
    assert client.get("/api/calendar/nope.ics", params={"token": token}).status_code == 404


def test_one_booking_downloads_as_its_own_file(client):
    codes = book(client, "9822200002")
    rt = server.runtime("dental_clinic")
    b = next(x for x in rt.backend.bookings("dental_clinic") if x.receipt_code == codes[-1])
    r = client.get(f"/api/bookings/dental_clinic/{b.booking_id}.ics")
    assert r.status_code == 200 and f"UID:{b.booking_id}@haanji" in r.text and "attachment" in r.headers["content-disposition"]
    assert client.get("/api/bookings/dental_clinic/nope.ics").status_code == 404


def test_long_lines_fold_and_text_escapes():
    long = cal._fold("DESCRIPTION:" + "x" * 200)
    assert all(len(l.encode()) <= 75 for l in long.split("\r\n")) and long.split("\r\n")[1].startswith(" ")
    assert cal._ics_escape("a,b;c\nd") == "a\\,b\\;c\\nd"


def test_google_oauth_and_push_through_a_fake_google(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, str(req.url)))
        if req.url.host == "oauth2.googleapis.com":
            data = dict(x.split("=") for x in req.content.decode().split("&"))
            if data.get("grant_type") == "authorization_code":
                assert data["code"] == "c0de"
                return httpx.Response(200, json={"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600})
            return httpx.Response(200, json={"access_token": "at2", "expires_in": 3600})
        if req.url.host == "www.googleapis.com":
            body = json.loads(req.content)
            assert req.headers["authorization"] == "Bearer at1" and body["start"]["timeZone"] == "Asia/Kolkata"
            return httpx.Response(200, json={"id": "evt123"})
        return httpx.Response(404)

    g = GoogleCalendar(str(tmp_path / "g.sqlite"), "cid", "csec", "https://haanji.example/api/google/callback",
                       transport=httpx.MockTransport(handler))
    assert g.configured
    url = g.connect_url("dental_clinic")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?") and "access_type=offline" in url
    state = url.split("state=")[1].split("&")[0]
    assert g.tenant_for_state("bogus") is None and g.tenant_for_state(state) == "dental_clinic"
    assert g.tenant_for_state(state) is None, "a state is single use"
    import asyncio
    asyncio.run(g.finish("dental_clinic", "c0de"))
    assert g.connected() == ["dental_clinic"]

    class B:
        booking_id, service, staff, date, time, duration_min = "b1", "root canal", "Dr Sheikh", "2026-09-08", "09:30", 45
        customer_name, phone, status, receipt_code = "Vijay Sharma", "9876543210", "CONFIRMED", "2504-7863"
    body = cal.google_event(B(), "Smile Care Dental", "https://haanji.example")
    assert body["end"]["dateTime"].startswith("2026-09-08T10:15") and "Verify:" in body["description"]
    assert asyncio.run(g.push("dental_clinic", "b1", body)) == "evt123"
    assert asyncio.run(g.push("dental_clinic", "b1", body)) == "evt123", "pushed once per booking"
    assert sum(1 for m, u in calls if "calendar/v3" in u) == 1
    assert g.disconnect("dental_clinic") and g.connected() == []


def test_google_endpoints_report_state_and_refuse_without_credentials(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "gcal", GoogleCalendar(str(tmp_path / "g.sqlite"), "", "", "x"))
    s = client.get("/api/google/status", params={"pack": "dental_clinic"}).json()
    assert s == {"configured": False, "connected": False, "connected_at": None, "redirect_uri": "x"}
    assert client.get("/api/google/connect", params={"pack": "dental_clinic"}).status_code == 409
    assert client.get("/api/google/callback", params={"code": "c", "state": "bad"}).status_code == 400
    assert client.get("/api/status").json()["google"] == {"configured": False, "connected": []}
