"""Backups of everything under HAANJI_VAR_DIR.

The managed host's disk is wiped on redeploy; the ledger is supposed to be
verifiable forever. Until the data lives in a real database, this is the
bridge: a consistent SQLite backup of every store into one tar.gz, nightly
and on demand, optionally pushed to S3-compatible storage, and restored on
boot from a URL or an object when the data directory is empty.

SQLite's online backup API is used (not a file copy), so a backup taken while
the server is writing is still consistent."""
from __future__ import annotations
import datetime as dt
import io
import logging
import os
import sqlite3
import tarfile
import tempfile
from typing import Iterable

log = logging.getLogger("haanji.backup")
KEEP_FILES = (".sqlite", ".json", ".secret", ".jsonl", ".yaml")


def _sqlite_bytes(path: str) -> bytes:
    src = sqlite3.connect(path)
    try:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            dst = sqlite3.connect(tmp.name)
            try:
                src.backup(dst)
            finally:
                dst.close()
            with open(tmp.name, "rb") as fh:
                data = fh.read()
        os.unlink(tmp.name)
        return data
    finally:
        src.close()


def make_backup(var_dir: str, out: io.BytesIO | None = None, *, include_recordings: bool = False) -> bytes:
    """Everything that matters in ``var_dir`` as a tar.gz (bytes)."""
    buf = out or io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(var_dir):
            rel_root = os.path.relpath(root, var_dir)
            if rel_root.startswith("recordings") and not include_recordings:
                continue
            for name in sorted(files):
                if not name.endswith(KEEP_FILES):
                    continue
                full = os.path.join(root, name)
                arc = os.path.normpath(os.path.join(rel_root, name)) if rel_root != "." else name
                data = _sqlite_bytes(full) if name.endswith(".sqlite") else open(full, "rb").read()
                info = tarfile.TarInfo(arc)
                info.size = len(data)
                info.mtime = int(dt.datetime.now().timestamp())
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def restore(var_dir: str, archive: bytes, *, only_if_empty: bool = True) -> list[str]:
    """Unpack a backup into ``var_dir``. By default refuses when the directory
    already holds data, so a stale backup cannot overwrite a live shop."""
    os.makedirs(var_dir, exist_ok=True)
    existing = [f for f in os.listdir(var_dir) if f.endswith(".sqlite")]
    if only_if_empty and existing:
        raise RuntimeError(f"{var_dir} already has {len(existing)} databases; pass only_if_empty=False to overwrite")
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or member.name.startswith(("/", "..")) or ".." in member.name.split("/"):
                continue
            target = os.path.join(var_dir, member.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh, tar.extractfile(member) as src:
                fh.write(src.read())
            written.append(member.name)
    return written


def backup_name(now: dt.datetime | None = None) -> str:
    return "haanji-" + (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ") + ".tar.gz"


# ------------------------------------------------------------- S3 (optional)
def s3_configured() -> bool:
    return bool(os.environ.get("HAANJI_BACKUP_S3_BUCKET"))


def upload_s3(data: bytes, name: str) -> str:
    """Put the archive in HAANJI_BACKUP_S3_BUCKET (prefix HAANJI_BACKUP_S3_PREFIX,
    endpoint HAANJI_BACKUP_S3_ENDPOINT for R2/MinIO). boto3 is the optional
    ``[backup]`` extra; the usual AWS_* variables carry the credentials."""
    import boto3                                              # the optional extra
    bucket = os.environ["HAANJI_BACKUP_S3_BUCKET"]
    key = os.environ.get("HAANJI_BACKUP_S3_PREFIX", "haanji/").rstrip("/") + "/" + name
    client = boto3.client("s3", endpoint_url=os.environ.get("HAANJI_BACKUP_S3_ENDPOINT") or None)
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/gzip")
    return f"s3://{bucket}/{key}"


def latest_s3() -> bytes | None:
    import boto3
    bucket = os.environ["HAANJI_BACKUP_S3_BUCKET"]
    prefix = os.environ.get("HAANJI_BACKUP_S3_PREFIX", "haanji/").rstrip("/") + "/"
    client = boto3.client("s3", endpoint_url=os.environ.get("HAANJI_BACKUP_S3_ENDPOINT") or None)
    listing = client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents") or []
    if not listing:
        return None
    newest = max(listing, key=lambda o: o["Key"])
    return client.get_object(Bucket=bucket, Key=newest["Key"])["Body"].read()


def restore_on_boot(var_dir: str) -> str | None:
    """HAANJI_RESTORE_FROM=<https url | s3> restores an empty data directory
    on start-up, so a redeploy does not start a real shop from zero."""
    source = os.environ.get("HAANJI_RESTORE_FROM")
    if not source:
        return None
    if any(f.endswith(".sqlite") for f in os.listdir(var_dir)) if os.path.isdir(var_dir) else False:
        return None
    try:
        if source == "s3":
            data = latest_s3()
        else:
            import httpx
            data = httpx.get(source, timeout=60, follow_redirects=True).content
        if not data:
            return None
        files = restore(var_dir, data)
        log.warning("restored %d files into %s from %s", len(files), var_dir, source)
        return source
    except Exception as exc:                                  # noqa: BLE001 - boot must go on
        log.warning("restore from %s failed: %s", source, exc)
        return None
