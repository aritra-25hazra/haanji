"""The four places GitHub's code scanning (CodeQL) pointed at that needed a
change. Each test fails if its guard is removed."""
import pytest
from fastapi.testclient import TestClient

from haanji import server

PACK = "dental_clinic"


@pytest.fixture
def client(monkeypatch):
    server._buckets.clear()
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    return TestClient(server.app)


@pytest.mark.parametrize("bad", ["..", "Dental_Clinic", "dental-clinic", "a" * 65, "%2e%2e"])
def test_a_pack_id_from_a_url_names_only_a_pack(client, bad):
    assert client.get(f"/api/packs/{bad}").status_code == 404
    with pytest.raises(server.HTTPException):
        server.pack_path(bad)


def test_a_real_pack_id_still_reads_its_file(client):
    r = client.get(f"/api/packs/{PACK}")
    assert r.status_code == 200 and r.json()["pack_id"] == PACK


def test_a_static_name_has_a_length_limit(client):
    assert client.get("/static/" + "a" * 81 + ".js").status_code == 404
    assert client.get("/static/signboard.css").status_code == 200


def test_a_failed_google_calendar_connect_shows_no_internals(client, monkeypatch, caplog):
    async def boom(pack, code):
        raise RuntimeError("token endpoint said: client_secret=hunter2 at /srv/app/gcal.py")
    monkeypatch.setattr(server.gcal, "tenant_for_state", lambda state: PACK)
    monkeypatch.setattr(server.gcal, "finish", boom)
    with caplog.at_level("WARNING", logger="haanji.server"):
        r = client.get("/api/google/callback", params={"code": "c", "state": "s"})
    assert r.status_code == 502
    assert "hunter2" not in r.text and "gcal.py" not in r.text and "RuntimeError" not in r.text
    assert "RuntimeError" in caplog.text and "hunter2" not in caplog.text


def test_the_demo_payment_page_escapes_the_shop_name(client, monkeypatch):
    rt = server.runtime(PACK)
    monkeypatch.setattr(rt.pack.persona, "business_name", '<script>alert("x")</script>')
    fake = {"payment_id": "pay_x", "tenant_id": PACK, "provider": "mock", "status": "CREATED",
            "amount_inr": 300, "link": "/pay/pay_x"}
    monkeypatch.setattr(server.payments, "get", lambda pid: dict(fake, payment_id=pid))
    r = client.get("/pay/pay_x")
    assert r.status_code == 200
    assert "<script>" not in r.text and "&lt;script&gt;" in r.text
    assert 'action="/pay/pay_x/mock-pay"' in r.text


@pytest.mark.parametrize("route", ["/api/lexicon", "/api/record/prompts"])
@pytest.mark.parametrize("bad", ["/etc/hosts", "../render.yaml", "../packs/dental_clinic.yaml"])
def test_a_pack_query_parameter_is_never_opened_as_a_path(client, route, bad):
    assert client.get(route, params={"pack": bad}).status_code == 404
    assert client.get(route, params={"pack": PACK}).status_code == 200
