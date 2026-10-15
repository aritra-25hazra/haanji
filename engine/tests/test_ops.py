"""Observability: where a turn's time went, and what a pager would watch."""
import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.scenario import scenarios_of
from haanji.telemetry import Telemetry
from haanji.vertical import load_pack


@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


def test_the_registry_renders_prometheus_text():
    t = Telemetry()
    t.inc("calls_total", pack="dental_clinic", outcome="BOOKED")
    t.inc("calls_total", pack="dental_clinic", outcome="BOOKED")
    t.observe("turn_latency_ms", 120.0, pack="dental_clinic")
    t.observe("turn_latency_ms", 900.0, pack="dental_clinic")
    t.gauge("live_sessions", 3)
    text = t.render()
    assert 'haanji_calls_total{outcome="BOOKED",pack="dental_clinic"} 2' in text
    assert "# TYPE haanji_turn_latency_ms histogram" in text
    assert 'haanji_turn_latency_ms_bucket{le="200",pack="dental_clinic"} 1' in text
    assert 'haanji_turn_latency_ms_bucket{le="+Inf",pack="dental_clinic"} 2' in text
    assert 'haanji_turn_latency_ms_count{pack="dental_clinic"} 2' in text
    assert "haanji_live_sessions 3" in text and "haanji_uptime_seconds" in text
    assert t.counter("calls_total", pack="dental_clinic", outcome="BOOKED") == 2 and t.total("calls_total") == 2


def test_a_call_leaves_spans_metrics_and_an_ops_view(client):
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9876543210"}).json()["session_id"]
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    payloads = [client.post(f"/api/sessions/{sid}/utterance", json={"text": u.truth}).json() for u in sc.utterances]
    first = payloads[0]
    assert first["spans"][0]["name"] == "bhasha" and any(sp["name"] == "dialogue" for sp in first["spans"])
    tool_spans = [sp for p in payloads for sp in p["spans"] if sp["name"].startswith("tool:")]
    assert any(sp["name"] == "tool:book_appointment" for sp in tool_spans)
    text = client.get("/metrics").text
    assert "haanji_turns_total" in text and "haanji_turn_latency_ms_bucket" in text
    assert 'haanji_calls_total{channel="web",outcome="BOOKED",pack="dental_clinic"}' in text
    assert "haanji_ledger_receipts_total" in text and 'haanji_tool_ms_bucket' in text
    ops = client.get("/api/ops", params={"pack": "dental_clinic"}).json()
    assert ops["slo"]["target_ms"] == 1500 and 0 <= ops["slo"]["within"] <= 1 and ops["turns"] >= 5
    assert sum(b["turns"] for b in ops["histogram"]) == ops["turns"]
    assert any(sp["name"] == "bhasha" for sp in ops["spans"])
    assert ops["latest_call"]["turns"][0]["spans"][0]["name"] == "bhasha"
    assert set(ops["counters"]) >= {"rate_limited", "auth_denied", "unconfirmed_refused"}


def test_the_ledger_counts_a_refused_unconfirmed_write():
    import sqlite3
    from haanji.pramaan.ledger import Ledger, LedgerError
    from haanji.telemetry import TELEMETRY
    before = TELEMETRY.counter("ledger_unconfirmed_refused_total", pack="t_ops")
    ledger = Ledger(sqlite3.connect(":memory:"))
    with pytest.raises(LedgerError):
        ledger.append(tenant_id="t_ops", conversation_id="c", action="book_appointment", action_args={},
                      confirmation=None, transcript_excerpt="", agent_config_version=1)
    assert TELEMETRY.counter("ledger_unconfirmed_refused_total", pack="t_ops") == before + 1
