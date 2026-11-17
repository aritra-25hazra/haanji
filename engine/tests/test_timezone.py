"""Times are stored in UTC with their offset and shown in India's time: at
21:15 IST the dashboard once showed a call at 15:45 and "peak 15:00"."""
import datetime as dt

from haanji import insights
from haanji.store import DemoStore, _now, to_ist


def test_a_stored_time_carries_its_offset():
    t = dt.datetime.fromisoformat(_now())
    assert t.utcoffset() == dt.timedelta(0)


def test_a_call_at_15_45_utc_is_21_15_in_india():
    assert to_ist("2026-11-17T15:45:00.000+00:00").strftime("%H:%M") == "21:15"
    assert to_ist("2026-11-17T19:00:00+00:00").date() == dt.date(2026, 11, 18), "after 18:30 UTC it is tomorrow in India"


def test_the_hourly_chart_and_today_count_in_india_s_time(tmp_path, backend):
    store = DemoStore(str(tmp_path / "calls.sqlite"))
    now_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rows = [("c1", now_utc.isoformat(), "BOOKED"), ("c2", "2026-01-05T15:45:00+00:00", "FAQ_ANSWERED")]
    for call_id, at, outcome in rows:
        store.conn.execute("INSERT INTO calls (call_id, tenant_id, channel, started_at, outcome) VALUES (?,?,?,?,?)",
                           (call_id, "t_test", "WEB", at, outcome))
    store.conn.commit()
    out = insights.compute("t_test", store, backend)
    hours = {h["hour"]: h["calls"] for h in out["by_hour"]}
    assert hours.get("21", 0) >= 1, "the 15:45 UTC call sits in India's 21:00 hour"
    assert f"{to_ist(now_utc.isoformat()).hour:02d}" in hours
    assert out["calls_today"] == 1, "only the call made today in India counts as today's"
    assert dt.datetime.fromisoformat(out["generated_at"]).utcoffset() is not None
