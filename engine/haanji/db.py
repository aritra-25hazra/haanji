"""Where the engine keeps its records: SQLite files (the default, nothing to
run) or PostgreSQL (HAANJI_DATABASE_URL=postgresql://…), which a managed host
keeps across redeploys.

Every store opens its database with :func:`connect`, passing the SQLite path
it always used. With Postgres configured, that path names a schema instead
(``backend-dental_clinic.sqlite`` → ``backend_dental_clinic``), so each file's
tables stay apart exactly as they did on disk, and the stores keep their
SQL: :class:`PgConnection` speaks the small part of the ``sqlite3`` interface
they use and translates SQLite's dialect on the way through:

* ``?`` placeholders, ``INSERT OR REPLACE`` / ``INSERT OR IGNORE``, ``LIKE``
  (case-insensitive in SQLite, so ``ILIKE`` here);
* DDL types: ``INTEGER`` → ``BIGINT``, ``REAL`` → ``DOUBLE PRECISION``,
  ``BLOB`` → ``BYTEA``, ``INTEGER PRIMARY KEY AUTOINCREMENT`` → ``BIGSERIAL``;
* ``PRAGMA table_info`` from the catalogue; other PRAGMAs are no-ops;
* an error inside a transaction rolls back that statement only (a savepoint
  per statement), as in SQLite; a unique violation raises
  ``sqlite3.IntegrityError`` so callers catch what they always caught.

Rows answer by column name and by position, like ``sqlite3.Row``.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import os
import re
import sqlite3
import threading
from typing import Any, Iterator, Sequence

URL_ENV = ("HAANJI_DATABASE_URL", "DATABASE_URL")


def database_url() -> str | None:
    for key in URL_ENV:
        url = os.environ.get(key)
        if url and url.startswith(("postgres://", "postgresql://")):
            return url
    return None


def connect(path: str, **kw: Any):
    """A connection for the store that used to live at ``path``."""
    url = database_url()
    if url is None or path == ":memory:":
        return sqlite3.connect(path, check_same_thread=False, **kw)
    return PgConnection(url, schema_for(path))


def schema_for(path: str) -> str:
    """``var/backend-dental_clinic.sqlite`` → ``backend_dental_clinic``. A path
    outside HAANJI_VAR_DIR (a test's temporary file) gets a short hash of its
    folder too, so two tests never share a schema."""
    base = re.sub(r"\.(sqlite3?|db)$", "", os.path.basename(path))
    name = re.sub(r"[^a-z0-9_]", "_", base.lower()).strip("_") or "haanji"
    var_dir = os.path.abspath(os.environ.get("HAANJI_VAR_DIR", "var"))
    folder = os.path.dirname(os.path.abspath(path))
    if folder != var_dir:
        name += "_" + hashlib.sha1(folder.encode()).hexdigest()[:8]
    return name[:60]


def archive(path: str, suffix: str) -> str:
    """Set a store aside whole, never rewritten: on Postgres its schema is
    renamed (``ledger_dental_clinic`` → ``ledger_dental_clinic_<suffix>``).
    Returns the new name. The caller has closed its connection."""
    import psycopg
    old = schema_for(path)
    new = f"{old}_{suffix}"[:63]
    with psycopg.connect(database_url(), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (old,)).fetchone()
        if exists:
            conn.execute(f'ALTER SCHEMA "{old}" RENAME TO "{new}"')
    return new


def open_schema(schema: str) -> "PgConnection":
    """A connection to a named schema (an archived store, for a check)."""
    return PgConnection(database_url() or "", schema)


LOCAL_ONLY = ("study.sqlite",)          # participants' answers never leave the host


def copy_sqlite_dir(var_dir: str) -> dict[str, dict[str, tuple[int, int]]]:
    """Copy every SQLite store under ``var_dir`` into the configured Postgres,
    table by table (``INSERT OR IGNORE``, so a re-run adds only what is
    missing), and return ``{file: {table: (rows in SQLite, rows in Postgres)}}``
    so the operator can see the two agree. The files are left as they are."""
    if database_url() is None:
        raise RuntimeError("set HAANJI_DATABASE_URL to the Postgres to copy into")
    report: dict[str, dict[str, tuple[int, int]]] = {}
    for name in sorted(os.listdir(var_dir)):
        if not name.endswith(".sqlite") or name in LOCAL_ONLY:
            continue
        path = os.path.join(var_dir, name)
        src = sqlite3.connect(path)
        dst = PgConnection(database_url() or "", schema_for(path))
        tables: dict[str, tuple[int, int]] = {}
        ddl = src.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for table, create in ddl:
            dst.execute(re.sub(r"^\s*CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?", "CREATE TABLE IF NOT EXISTS ", create, flags=re.I))
            cur = src.execute(f'SELECT * FROM "{table}"')
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            marks = ",".join("?" * len(cols))
            for row in rows:
                dst.execute(f'INSERT OR IGNORE INTO {table} ({", ".join(cols)}) VALUES ({marks})', row)
            dst.commit()
            copied = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            tables[table] = (len(rows), copied)
        for (index_sql,) in src.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
            dst.execute(re.sub(r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(IF\s+NOT\s+EXISTS\s+)?",
                               lambda m: f"CREATE {m.group(1) or ''}INDEX IF NOT EXISTS ", index_sql, flags=re.I))
        dst.commit()
        dst.close()
        src.close()
        report[name] = tables
    return report


# ───────────────────────────────────────────────────────── the dialect
_TYPES = [(re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.I), "BIGSERIAL PRIMARY KEY"),
          (re.compile(r"\bINTEGER\b", re.I), "BIGINT"),
          (re.compile(r"\bREAL\b", re.I), "DOUBLE PRECISION"),
          (re.compile(r"\bBLOB\b", re.I), "BYTEA")]
_DDL = re.compile(r"^\s*(CREATE|ALTER)\s", re.I)
_INSERT_OR = re.compile(r"^\s*INSERT\s+OR\s+(REPLACE|IGNORE)\s+INTO\s+([A-Za-z_][\w]*)\s*(\(([^)]*)\))?", re.I | re.S)
_PRAGMA_INFO = re.compile(r"^\s*PRAGMA\s+table_info\(\s*([A-Za-z_]\w*)\s*\)\s*$", re.I)
_LIKE = re.compile(r"\bLIKE\b", re.I)


def _placeholders(sql: str, named: bool = False) -> str:
    """``?`` → ``%s`` (or ``:name`` → ``%(name)s``) outside string literals;
    a literal ``%`` is doubled."""
    out, quote, i = [], None, 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append("%%" if ch == "%" else ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "?" and not named:
            out.append("%s")
        elif ch == ":" and named and i + 1 < len(sql) and (sql[i + 1].isalpha() or sql[i + 1] == "_"):
            j = i + 1
            while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            out.append(f"%({sql[i + 1:j]})s")
            i = j
            continue
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split(script: str) -> list[str]:
    """Statements of a schema script; ``--`` comments go first (one of them
    may hold a semicolon)."""
    script = re.sub(r"--[^\n]*", "", script)
    return [s.strip() for s in script.split(";") if s.strip()]


def _param(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return str(v)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


class PgRow(tuple):
    """A row that answers by position and by column name, like sqlite3.Row."""

    def __new__(cls, values: Sequence[Any], names: Sequence[str]):
        row = super().__new__(cls, values)
        row._names = tuple(names)
        return row

    def __getitem__(self, key):                          # type: ignore[override]
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._names.index(key))
            except ValueError:
                raise IndexError(f"no such column: {key}") from None
        return tuple.__getitem__(self, key)

    def keys(self) -> list[str]:
        return list(self._names)


class PgCursor:
    def __init__(self, rows: list[PgRow], rowcount: int):
        self._rows, self.rowcount, self._i = rows, rowcount, 0
        self.lastrowid = None

    def fetchone(self) -> PgRow | None:
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self) -> list[PgRow]:
        rest, self._i = self._rows[self._i:], len(self._rows)
        return rest

    def __iter__(self) -> Iterator[PgRow]:
        return iter(self.fetchall())


class PgConnection:
    """The slice of sqlite3.Connection the engine's stores use, on Postgres."""

    def __init__(self, url: str, schema: str):
        import psycopg  # the optional [postgres] extra
        self._psycopg = psycopg
        self.schema = schema
        self._conn = psycopg.connect(url, autocommit=False)
        self._lock = threading.RLock()
        self._depth = 0                                    # `with conn:` nesting
        self._tables: dict[str, tuple[list[str], list[str]]] = {}
        self.row_factory = None                            # accepted and ignored: rows are always PgRow
        with self._conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cur.execute(f'SET search_path TO "{schema}"')
        self._conn.commit()

    # -------------------------------------------------------------- dialect
    def _columns(self, table: str) -> tuple[list[str], list[str]]:
        """(every column in order, the primary key's columns) of a table."""
        if table not in self._tables:
            with self._conn.cursor() as cur:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s"
                            " ORDER BY ordinal_position", (self.schema, table.lower()))
                cols = [r[0] for r in cur.fetchall()]
                cur.execute("SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid"
                            " AND a.attnum = ANY(i.indkey) WHERE i.indrelid=%s::regclass AND i.indisprimary",
                            (f'"{self.schema}"."{table.lower()}"',))
                pk = [r[0] for r in cur.fetchall()]
            self._tables[table] = (cols, pk)
        return self._tables[table]

    def _translate(self, sql: str) -> str:
        if _DDL.match(sql):
            for rx, repl in _TYPES:
                sql = rx.sub(repl, sql)
            if re.match(r"^\s*CREATE\s", sql, re.I):
                self._tables.clear()
            return sql
        m = _INSERT_OR.match(sql)
        if m:
            mode, table, cols_text = m.group(1).upper(), m.group(2), m.group(4)
            sql = "INSERT INTO " + sql[m.start(2):]
            if mode == "IGNORE":
                return sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
            cols, pk = self._columns(table)
            given = [c.strip() for c in cols_text.split(",")] if cols_text else cols
            update = [c for c in given if c not in pk]
            if not pk:
                return sql
            action = ("DO UPDATE SET " + ", ".join(f"{c}=EXCLUDED.{c}" for c in update)) if update else "DO NOTHING"
            return sql.rstrip().rstrip(";") + f" ON CONFLICT ({', '.join(pk)}) {action}"
        return _LIKE.sub("ILIKE", sql)

    # ------------------------------------------------------------ interface
    def execute(self, sql: str, params: Sequence[Any] | dict | None = None) -> PgCursor:
        with self._lock:
            info = _PRAGMA_INFO.match(sql)
            if info:
                cols, _pk = self._columns(info.group(1))
                return PgCursor([PgRow((i, c), ("cid", "name")) for i, c in enumerate(cols)], len(cols))
            if re.match(r"^\s*PRAGMA\b", sql, re.I):
                return PgCursor([], 0)
            text = self._translate(sql)
            named = isinstance(params, dict)
            args: Any = ({k: _param(v) for k, v in params.items()} if named else [_param(v) for v in params]) if params else None
            text = _placeholders(text, named) if args else text
            with self._conn.cursor() as cur:
                cur.execute("SAVEPOINT haanji_stmt")
                try:
                    cur.execute(text, args)
                except self._psycopg.errors.IntegrityError as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT haanji_stmt")
                    raise sqlite3.IntegrityError(str(exc)) from exc
                except self._psycopg.Error:
                    cur.execute("ROLLBACK TO SAVEPOINT haanji_stmt")
                    raise
                rows: list[PgRow] = []
                if cur.description:
                    names = [d.name for d in cur.description]
                    rows = [PgRow(r, names) for r in cur.fetchall()]
                count = cur.rowcount
                cur.execute("RELEASE SAVEPOINT haanji_stmt")
            if _DDL.match(sql):
                self._tables.clear()
            return PgCursor(rows, count)

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> PgCursor:
        total = 0
        for params in seq:
            total += self.execute(sql, params).rowcount
        return PgCursor([], total)

    def executescript(self, script: str) -> None:
        for statement in _split(script):
            self.execute(statement)
        self.commit()

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()

    def __enter__(self) -> "PgConnection":
        self._lock.acquire()
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._depth == 1:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            self._depth -= 1
            self._lock.release()
