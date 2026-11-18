"""Times are stored in UTC with their offset and shown in India's time: at
21:15 IST the dashboard once showed a call at 15:45 and "peak 15:00"."""
import datetime as dt

from haanji import insights
from haanji.store import IST, DemoStore, _now, to_ist


def test_a_stored_time_carries_its_offset():
    t = dt.datetime.fromisoformat(_now())
    assert t.utcoffset() == dt.timedelta(0)


def test_a_call_at_15_45_utc_is_21_15_in_india():
    assert to_ist("2026-11-17T15:45:00.000+00:00").strftime("%H:%M") == "21:15"
    assert to_ist("2026-11-17T19:00:00+00:00").date() == dt.date(2026, 11, 18), "after 18:30 UTC it is tomorrow in India"


def test_the_hourly_chart_and_today_count_in_india_s_time(tmp_path, backend):
    store = DemoStore(str(tmp_path / "calls.sqlite"))
    now_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rows = [("c1", now_utc.isoformat(), "BOOKED"), ("c2", "2026-01-05T15:45:00+00:00", "FAQ_ANSWERED"),
            ("c3", "2026-01-05T19:00:00+00:00", "FAQ_ANSWERED")]
    for call_id, at, outcome in rows:
        store.conn.execute("INSERT INTO calls (call_id, tenant_id, channel, started_at, outcome) VALUES (?,?,?,?,?)",
                           (call_id, "t_test", "WEB", at, outcome))
    store.conn.commit()
    out = insights.compute("t_test", store, backend)
    hours = {h["hour"]: h["calls"] for h in out["by_hour"]}
    assert hours == {f"{to_ist(now_utc.isoformat()).hour:02d}": 1}, "the chart is today's, in India's hours"
    assert out["calls_today"] == 1, "only the call made today in India counts as today's"
    assert dt.datetime.fromisoformat(out["generated_at"]).utcoffset() is not None
    # Late on 5 January in India, the 15:45 UTC call sits in the 21:00 hour; the
    # 19:00 UTC one is already 00:30 on the 6th there, so it is tomorrow's.
    late = insights.compute("t_test", store, backend, now=dt.datetime(2026, 1, 5, 23, 0, tzinfo=IST))
    assert {h["hour"]: h["calls"] for h in late["by_hour"]} == {"21": 1} and late["calls_today"] == 1
    early = insights.compute("t_test", store, backend, now=dt.datetime(2026, 1, 6, 0, 40, tzinfo=IST))
    assert {h["hour"]: h["calls"] for h in early["by_hour"]} == {"00": 1} and early["day"] == "2026-01-06"


def test_the_cost_comparison_and_yesterday_s_calls_follow_the_shop(tmp_path, backend):
    store = DemoStore(str(tmp_path / "calls.sqlite"))
    yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    store.conn.execute("INSERT INTO calls (call_id, tenant_id, channel, started_at, outcome) VALUES (?,?,?,?,?)",
                       ("y1", "t_test", "WEB", yesterday, "BOOKED"))
    store.conn.commit()
    out = insights.compute("t_test", store, backend, {"receptionist_monthly_inr": 15000, "receptionist_calls_per_month": 1000})
    assert out["cost"]["receptionist_per_call_inr"] == 15.0
    assert out["cost"]["assumptions"]["receptionist_monthly"] == 15000
    assert out["calls_yesterday"] == 1 and out["calls_today"] == 0
    empty = insights.compute("t_test", DemoStore(str(tmp_path / "none.sqlite")), backend)
    assert not any("kharcha" in line for line in empty["insights"]), "no cost line without a call"
