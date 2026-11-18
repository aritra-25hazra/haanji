"""The engine's records in SQLite files (default) or PostgreSQL
(HAANJI_DATABASE_URL). The stores keep their SQLite SQL; haanji.db speaks it
to Postgres. The dialect tests run everywhere; the rest run when a Postgres
is configured (CI's postgres job runs the whole suite that way)."""
import sqlite3

import pytest

from haanji import db

PG = db.database_url()
needs_pg = pytest.mark.skipif(not PG, reason="set HAANJI_DATABASE_URL to a Postgres to run these")


def test_placeholders_change_only_outside_string_literals():
    assert db._placeholders("SELECT * FROM t WHERE a=? AND b='x?' AND c LIKE '%y%'") == \
        "SELECT * FROM t WHERE a=%s AND b='x?' AND c LIKE '%%y%%'"
    assert db._placeholders("VALUES (:a, :b_2, '12:30')", named=True) == "VALUES (%(a)s, %(b_2)s, '12:30')"


def test_schema_scripts_lose_their_comments_before_splitting():
    script = "CREATE TABLE a (x TEXT); -- a note; with a semicolon\nCREATE TABLE b (y TEXT);"
    assert db._split(script) == ["CREATE TABLE a (x TEXT)", "CREATE TABLE b (y TEXT)"]


def test_without_a_postgres_url_every_store_is_a_sqlite_file(tmp_path, monkeypatch):
    for key in db.URL_ENV:
        monkeypatch.delenv(key, raising=False)
    conn = db.connect(str(tmp_path / "x.sqlite"))
    assert isinstance(conn, sqlite3.Connection)
    monkeypatch.setenv("DATABASE_URL", "mysql://nope")
    assert db.database_url() is None, "only a postgres URL switches"


def test_a_store_s_schema_name_follows_its_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HAANJI_VAR_DIR", str(tmp_path))
    assert db.schema_for(str(tmp_path / "backend-dental_clinic.sqlite")) == "backend_dental_clinic"
    other = db.schema_for("/somewhere/else/auth.sqlite")
    assert other.startswith("auth_") and other != "auth"


@needs_pg
def test_the_sqlite_dialect_works_on_postgres(tmp_path):
    conn = db.connect(str(tmp_path / "dialect.sqlite"))
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, n INTEGER NOT NULL DEFAULT 0, t REAL);
      CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, msg TEXT);  -- serial; really
    """)
    conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?,?)", ("a", "Asha", 1, 1_800_000_000.125))
    conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?,?)", ("a", "Asha Rao", 2, 1_800_000_000.25))
    conn.execute("INSERT OR IGNORE INTO kv (k, v) VALUES (?,?)", ("a", "ignored"))
    conn.commit()
    row = conn.execute("SELECT * FROM kv WHERE k=?", ("a",)).fetchone()
    assert row["v"] == "Asha Rao" and row[2] == 2 and row["t"] == 1_800_000_000.25 and dict(row)["k"] == "a"
    assert conn.execute("SELECT v FROM kv WHERE v LIKE ?", ("%asha%",)).fetchone()[0] == "Asha Rao", "LIKE ignores case, as in SQLite"
    assert [r["name"] for r in conn.execute("PRAGMA table_info(kv)")] == ["k", "v", "n", "t"]
    conn.execute("INSERT INTO log (msg) VALUES (?)", ("one",))
    conn.execute("INSERT INTO log (msg) VALUES (?)", ("two",))
    assert [r["id"] for r in conn.execute("SELECT id FROM log ORDER BY id")] == [1, 2]


@needs_pg
def test_a_failed_statement_undoes_itself_only(tmp_path):
    conn = db.connect(str(tmp_path / "tx.sqlite"))
    conn.execute("CREATE TABLE IF NOT EXISTS u (k TEXT PRIMARY KEY)")
    conn.commit()
    with conn:
        conn.execute("INSERT INTO u VALUES (?)", ("kept",))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO u VALUES (?)", ("kept",))
        conn.execute("INSERT INTO u VALUES (?)", ("also kept",))
    assert {r[0] for r in conn.execute("SELECT k FROM u")} == {"kept", "also kept"}


@needs_pg
def test_with_postgres_the_backup_download_points_at_the_database_host():
    from fastapi.testclient import TestClient
    from haanji import server
    r = TestClient(server.app).get("/api/admin/backup")
    assert r.status_code == 409 and "PostgreSQL" in r.json()["detail"]


@needs_pg
def test_a_sqlite_data_directory_moves_to_postgres_whole_and_the_chain_still_verifies(tmp_path):
    import os
    from haanji.pramaan.ledger import Ledger
    from haanji.pramaan.verifier import verify_chain
    from haanji.store import DemoStore
    folder = tmp_path / "var"
    folder.mkdir()
    from haanji.pramaan.receipt import ConfirmationProof
    src = sqlite3.connect(str(folder / "ledger-t.sqlite"))     # written as a SQLite deployment would
    led = Ledger(src)
    proof = ConfirmationProof(prompt_text="Confirm kar dun?", prompt_start_ms=0, reply_text="haan",
                              reply_start_ms=900, asr_confidence=0.9)
    for i in range(3):
        led.append(tenant_id="t", conversation_id=f"c{i}", action="book_appointment",
                   action_args={"service": "cleaning", "i": i}, confirmation=proof, transcript_excerpt="haan")
    src.close()
    store_file = sqlite3.connect(str(folder / "store.sqlite"))
    store_file.executescript(__import__("haanji.store", fromlist=["SCHEMA"]).SCHEMA)
    store_file.execute("INSERT INTO calls (call_id, tenant_id, channel, started_at, outcome) VALUES ('c1','t','WEB','2026-11-18T05:00:00+00:00','BOOKED')")
    store_file.commit()
    store_file.close()
    (folder / "study.sqlite").write_bytes(b"")              # participants' answers are never copied
    report = db.copy_sqlite_dir(str(folder))
    assert "study.sqlite" not in report
    assert report["ledger-t.sqlite"]["receipts"] == (3, 3) and report["store.sqlite"]["calls"] == (1, 1)
    moved = Ledger(db.connect(str(folder / "ledger-t.sqlite")))
    receipts = moved.receipts("t")
    public = moved.public_key(moved.ensure_key("t"))
    assert len(receipts) == 3 and verify_chain(receipts, lambda _k: public).ok
    assert db.copy_sqlite_dir(str(folder))["ledger-t.sqlite"]["receipts"] == (3, 3), "a re-run adds nothing twice"
    assert DemoStore(str(folder / "store.sqlite")).calls("t")[0]["call_id"] == "c1"
