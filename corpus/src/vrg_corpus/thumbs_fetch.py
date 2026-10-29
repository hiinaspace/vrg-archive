"""Polite, resumable fetch of 4chan-size thumbnails from arch.b4k.dev (foolfuuka API).

One thread-level API request per thread gives every post's ``thumb_link``; each thumbnail is
then fetched once. Files are content-addressed by the 4chan image md5
(``raw/<md5[:2]>/<md5>.jpg``), so reposts are fetched once. Progress lives in
``state.sqlite`` next to the store: killing and restarting the process loses nothing.

Politeness: one identifying User-Agent, one connection, strictly sequential, at most 2
requests/s whatever ``interval`` says, Retry-After honoured, exponential back-off on 429/403,
and a STOP file (the run refuses to start while it exists) after 3 such events in an hour.

Only non-deleted posts whose file is not deleted are ever requested. Nothing here reads or
writes the live scraper DB: inputs are the merged corpus and a snapshot copy used only to
skip posts that already have a 4chan thumbnail BLOB.
"""

from __future__ import annotations

import base64
import binascii
import http.client
import io
import json
import signal
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

UA = "vrg-archive (hiina@hiina.space)"
HOST = "arch.b4k.dev"
MIN_INTERVAL = 0.5  # hard floor: never more than 2 requests/s
SINCE_DEFAULT = 1566777600  # 2019-08-26 00:00 UTC, b4k's /vg/ starts about here
STORE_DEFAULT = Path("/mnt/pool/vrg-archive/thumbs")
LOG_EVERY = 3600.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS thread (
  thread_no INTEGER PRIMARY KEY, status TEXT NOT NULL, http INTEGER,
  n_target INTEGER, n_links INTEGER, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS thumb (
  no INTEGER PRIMARY KEY, thread_no INTEGER NOT NULL, md5 TEXT NOT NULL, url TEXT,
  w INTEGER, h INTEGER, status TEXT NOT NULL, http INTEGER, bytes INTEGER, note TEXT,
  fetched_at TEXT);
CREATE INDEX IF NOT EXISTS thumb_thread ON thumb(thread_no, status);
CREATE INDEX IF NOT EXISTS thumb_md5 ON thumb(md5);
CREATE TABLE IF NOT EXISTS event (at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT);
"""
# thumb.status: pending | ok (fetched) | dup (md5 already in store) | nolink (not in b4k)
#               | 404 | bad (failed verification) | err (retried on next start)


class Stop(Exception):
    """Run must end (STOP file written or SIGTERM)."""


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def md5_path(store: Path, md5: str) -> Path:
    return store / "raw" / md5[:2] / f"{md5}.jpg"


def b64_to_hex(h: str) -> str | None:
    try:
        out = binascii.hexlify(base64.b64decode(h)).decode()
    except (binascii.Error, ValueError):
        return None
    return out if len(out) == 32 else None


def verify_jpeg(data: bytes, want_w: int | None, want_h: int | None) -> tuple[int, int, str]:
    """(w, h, '') when ``data`` decodes as a JPEG of the expected size, else (0, 0, reason)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            w, h = im.size
            im.load()
    except Exception as e:  # noqa: BLE001 - any decode failure is a verification failure
        return 0, 0, f"undecodable: {e!r}"[:200]
    if fmt != "JPEG":
        return 0, 0, f"format {fmt}"
    if want_w and want_h and (w, h) != (want_w, want_h):
        return w, h, f"size {w}x{h} != api {want_w}x{want_h}"
    return w, h, ""


class Client:
    """One keep-alive HTTPS connection, request spacing, back-off, STOP policy."""

    def __init__(self, store: Path, state: sqlite3.Connection, interval: float) -> None:
        self.store = store
        self.db = state
        self.interval = max(interval, MIN_INTERVAL)
        self.last = 0.0
        self.conn: http.client.HTTPSConnection | None = None
        self.requests = 0
        self.stopping = False
        self.consec_fail = 0

    def stop_file(self) -> Path:
        return self.store / "STOP"

    def _write_stop(self, why: str) -> None:
        self.stop_file().write_text(f"{now_iso()} {why}\n")
        raise Stop(why)

    def _throttle_event(self, kind: str, detail: str, retry_after: float | None) -> None:
        t = time.time()
        self.db.execute("INSERT INTO event VALUES (?,?,?)", (t, kind, detail))
        self.db.commit()
        n = self.db.execute(
            "SELECT count(*) FROM event WHERE kind='throttle' AND at > ?", (t - 3600,)
        ).fetchone()[0]
        if n >= 3:
            self._write_stop(
                f"{n} HTTP 429/403 responses within an hour (last: {detail}); stopped by policy. "
                f"Delete {self.stop_file()} to allow a restart."
            )
        wait = max(retry_after or 0.0, 300.0 * 2 ** (n - 1))
        log(f"throttled ({detail}); event {n}/3 in the last hour; sleeping {wait:.0f}s")
        self.sleep(wait)

    def sleep(self, secs: float) -> None:
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if self.stopping:
                raise Stop("SIGTERM")
            time.sleep(min(1.0, end - time.monotonic()))

    def get(self, path: str) -> tuple[int, bytes]:
        """GET ``path`` with spacing and retries. Returns (status, body); 0 after 4 failures."""
        for attempt in range(5):
            if self.stopping:
                raise Stop("SIGTERM")
            if self.stop_file().exists():
                raise Stop("STOP file present")
            d = self.interval - (time.monotonic() - self.last)
            if d > 0:
                time.sleep(d)
            self.last = time.monotonic()
            self.requests += 1
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=30)
                self.conn.request(
                    "GET", path, headers={"User-Agent": UA, "Accept-Encoding": "identity"}
                )
                r = self.conn.getresponse()
                body = r.read()
                status = r.status
                ra = r.getheader("Retry-After")
                if r.getheader("Connection", "").lower() == "close":
                    self.conn.close()
                    self.conn = None
            except (OSError, http.client.HTTPException) as e:
                self.conn = None
                self.consec_fail += 1
                if self.consec_fail >= 10:
                    self._write_stop(f"10 consecutive transport failures, last {e!r}")
                wait = min(10 * 2**attempt, 300)
                log(f"transport error {e!r} on {path}; retry in {wait}s")
                self.sleep(wait)
                continue
            if status in (429, 403):
                self.conn = None
                try:
                    retry_after = float(ra) if ra else None
                except ValueError:
                    retry_after = None
                self._throttle_event("throttle", f"HTTP {status} {path}", retry_after)
                continue
            if status in (500, 502, 503, 504):
                self.consec_fail += 1
                if self.consec_fail >= 10:
                    self._write_stop(f"10 consecutive failures, last HTTP {status} {path}")
                try:
                    wait = float(ra) if ra else min(10 * 2**attempt, 300)
                except ValueError:
                    wait = 30
                log(f"HTTP {status} on {path}; retry in {wait:.0f}s")
                self.sleep(wait)
                continue
            self.consec_fail = 0
            return status, body
        return 0, b""


def log(msg: str) -> None:
    print(f"{now_iso()} {msg}", flush=True)


def targets(corpus: Path, blob_db: Path | None, since: int) -> dict[int, list[tuple[int, str]]]:
    """{thread_no: [(post no, md5)]} for non-deleted image posts with no 4chan BLOB."""
    con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    have: set[int] = set()
    if blob_db is not None:
        b = sqlite3.connect(f"file:{blob_db}?mode=ro", uri=True)
        have = {r[0] for r in b.execute("SELECT no FROM posts WHERE thumbnail IS NOT NULL")}
        b.close()
    out: dict[int, list[tuple[int, str]]] = {}
    for no, thread_no, md5 in con.execute(
        "SELECT no, thread_no, file_md5 FROM post WHERE file_ext IS NOT NULL AND deleted = 0 "
        "AND file_deleted = 0 AND file_md5 IS NOT NULL AND time >= ? ORDER BY no",
        (since,),
    ):
        if no not in have:
            out.setdefault(thread_no, []).append((no, md5))
    con.close()
    return out


def open_state(store: Path) -> sqlite3.Connection:
    store.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(store / "state.sqlite", timeout=60)
    db.execute("PRAGMA journal_mode=DELETE")  # the store may live on sshfs: no WAL
    db.executescript(SCHEMA)
    db.commit()
    return db


def load_thread(
    client: Client, thread_no: int, want: list[tuple[int, str]]
) -> tuple[str, int, list[tuple]]:
    """API request for one thread -> (thread status, http, thumb rows)."""
    status, body = client.get(f"/_/api/chan/thread/?board=vg&num={thread_no}")
    if status == 0:
        raise RuntimeError(f"thread {thread_no}: no response")
    nolink = [(no, thread_no, md5, None, None, None, "nolink", None) for no, md5 in want]
    if status != 200:
        return f"http{status}", status, nolink
    try:
        j = json.loads(body)
    except json.JSONDecodeError:
        return "badjson", status, nolink
    t = j.get(str(thread_no)) if isinstance(j, dict) else None
    if not isinstance(t, dict):
        return "notfound", status, nolink
    posts = dict(t.get("posts") or {})
    if t.get("op"):
        posts[str(thread_no)] = t["op"]
    rows = []
    for no, md5 in want:
        p = posts.get(str(no))
        m = p.get("media") if isinstance(p, dict) else None
        if (
            not isinstance(m, dict)
            or not m.get("thumb_link")
            or m.get("banned") not in (None, "0", 0)
        ):
            rows.append((no, thread_no, md5, None, None, None, "nolink", None))
            continue
        link = m["thumb_link"]
        h = b64_to_hex(m.get("media_hash") or "")
        if h != md5:
            rows.append((no, thread_no, md5, link, None, None, "bad", f"md5 mismatch api={h}"))
            continue
        w = int(m["preview_w"]) if str(m.get("preview_w") or "").isdigit() else None
        hh = int(m["preview_h"]) if str(m.get("preview_h") or "").isdigit() else None
        rows.append((no, thread_no, md5, link, w, hh, "pending", None))
    return "ok", status, rows


def fetch_one(
    client: Client, store: Path, no: int, md5: str, url: str, w: int | None, h: int | None
) -> tuple[str, int, int, str]:
    """-> (status, http, bytes, note)."""
    dest = md5_path(store, md5)
    if dest.exists() and dest.stat().st_size > 0:
        return "dup", 0, dest.stat().st_size, ""
    path = url.split(HOST, 1)[1] if HOST in url else None
    if path is None:
        return "bad", 0, 0, f"unexpected host in {url}"
    status, body = client.get(path)
    if status == 0:
        return "err", 0, 0, "no response"
    if status == 404:
        return "404", 404, 0, ""
    if status != 200:
        return "err", status, 0, f"HTTP {status}"
    rw, rh, why = verify_jpeg(body, w, h)
    if why:
        return "bad", status, len(body), why
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.rename(dest)
    return "ok", status, len(body), ""


def run(
    corpus: Path,
    blob_db: Path | None,
    store: Path = STORE_DEFAULT,
    interval: float = 1.0,
    since: int = SINCE_DEFAULT,
    limit: int | None = None,
) -> int:
    """Run or resume. Returns 0 when complete, 3 when stopped by policy, 2 on SIGTERM."""
    if (store / "STOP").exists():
        log(f"STOP file present: {(store / 'STOP').read_text().strip()}")
        return 3
    db = open_state(store)
    client = Client(store, db, interval)
    signal.signal(signal.SIGTERM, lambda *_: setattr(client, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(client, "stopping", True))
    tg = targets(corpus, blob_db, since)
    threads = sorted(tg, reverse=True)  # newest first
    n_posts = sum(len(v) for v in tg.values())
    log(f"targets: {n_posts} posts in {len(threads)} threads; interval {client.interval}s")
    done_threads = {r[0] for r in db.execute("SELECT thread_no FROM thread")}
    t0 = time.monotonic()
    last_log = t0
    fetched = 0
    counts: dict[str, int] = {}
    try:
        for ti, thread_no in enumerate(threads):
            want = tg[thread_no]
            if thread_no not in done_threads:
                tstatus, http_code, rows = load_thread(client, thread_no, want)
                nl = sum(1 for r in rows if r[6] != "nolink")
                db.executemany(
                    "INSERT OR IGNORE INTO thumb (no, thread_no, md5, url, w, h, status, note) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    rows,
                )
                db.execute(
                    "INSERT OR REPLACE INTO thread VALUES (?,?,?,?,?,?)",
                    (thread_no, tstatus, http_code, len(want), nl, now_iso()),
                )
                db.commit()
            pend = db.execute(
                "SELECT no, md5, url, w, h FROM thumb WHERE thread_no=? "
                "AND status IN ('pending','err') ORDER BY no",
                (thread_no,),
            ).fetchall()
            for no, md5, url, w, h in pend:
                st, code, nbytes, note = fetch_one(client, store, no, md5, url, w, h)
                db.execute(
                    "UPDATE thumb SET status=?, http=?, bytes=?, note=?, fetched_at=? WHERE no=?",
                    (st, code, nbytes, note, now_iso(), no),
                )
                db.commit()
                counts[st] = counts.get(st, 0) + 1
                fetched += 1
                if st in ("bad", "err"):
                    log(f"post {no} {st}: {note}")
                if time.monotonic() - last_log >= LOG_EVERY:
                    last_log = time.monotonic()
                    progress(db, client, t0, ti, len(threads), counts)
                if limit and fetched >= limit:
                    raise Stop(f"--limit {limit} reached")
            if time.monotonic() - last_log >= LOG_EVERY:
                last_log = time.monotonic()
                progress(db, client, t0, ti, len(threads), counts)
        progress(db, client, t0, len(threads), len(threads), counts)
        log("complete")
        return 0
    except Stop as e:
        log(f"stopping: {e}")
        progress(db, client, t0, 0, len(threads), counts)
        return 3 if (store / "STOP").exists() else 2
    finally:
        db.commit()
        db.close()


def progress(
    db: sqlite3.Connection, client: Client, t0: float, ti: int, nthreads: int, counts: dict
) -> None:
    el = time.monotonic() - t0
    rows = dict(db.execute("SELECT status, count(*) FROM thumb GROUP BY status").fetchall())
    left = rows.get("pending", 0) + rows.get("err", 0)
    rate = client.requests / el if el > 0 else 0.0
    log(
        f"progress: thread {ti}/{nthreads}; {client.requests} requests in {el / 3600:.2f}h "
        f"({rate:.2f}/s); this run {counts}; store {rows}; pending known {left}"
    )
