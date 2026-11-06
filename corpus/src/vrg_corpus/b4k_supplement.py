"""Supplement source: posts that b4k (foolfuuka API) has and neither source snapshot holds.

``fetch`` makes one API request per named thread through the polite thumbs_fetch client, keeps only
posts absent from both snapshots and writes a deterministic JSONL (sorted by post number).
``rows`` loads that file as parquet-shaped dicts for ``normalize.from_b4k``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import duckdb

from . import thumbs_fetch as tf

THREADS = (523150896, 571893181, 579640752, 585059270)
MEDIA_KEYS = (
    "media_filename",
    "media_w",
    "media_h",
    "media_size",
    "media_hash",
    "spoiler",
    "banned",
    "media_status",
    "thumb_link",
    "preview_w",
    "preview_h",
)
POST_KEYS = ("num", "thread_num", "op", "timestamp", "capcode", "name", "trip", "title", "comment")
FILENAME = "b4k-supplement.jsonl"


def snapshot_nos(snapdir: Path) -> set[int]:
    from .build import LIVE, PARQUET

    db = sqlite3.connect(f"file:{snapdir / LIVE}?mode=ro", uri=True)
    have = {int(r[0]) for r in db.execute("select no from posts")}
    db.close()
    con = duckdb.connect()
    have |= {
        int(r[0])
        for r in con.execute(
            f"select post_num from read_parquet('{snapdir / PARQUET}') "
            "where subnum is null or subnum = 0"
        ).fetchall()
    }
    return have


def select_posts(thread_json: dict[str, Any], thread_no: int, have: set[int]) -> list[dict]:
    """Reduce one API thread response to the kept fields of posts not in ``have``."""
    t = thread_json.get(str(thread_no))
    if not isinstance(t, dict):
        raise RuntimeError(f"thread {thread_no}: not in API response")
    posts = dict(t.get("posts") or {})
    if t.get("op"):
        posts[str(thread_no)] = t["op"]
    out = []
    for p in posts.values():
        if str(p.get("subnum") or "0") != "0" or int(p["num"]) in have:
            continue
        rec: dict[str, Any] = {k: p.get(k) for k in POST_KEYS}
        rec["deleted"] = p.get("deleted")
        m = p.get("media")
        rec["media"] = {k: m.get(k) for k in MEDIA_KEYS} if isinstance(m, dict) else None
        out.append(rec)
    return sorted(out, key=lambda r: int(r["num"]))


def fetch(snapdir: Path, out: Path, threads: tuple[int, ...] = THREADS, interval: float = 1.0):
    import tempfile

    have = snapshot_nos(snapdir)
    with tempfile.TemporaryDirectory() as td:
        store = Path(td)
        db = tf.open_state(store)
        client = tf.Client(store, db, interval)
        recs: list[dict] = []
        for n in threads:
            status, body = client.get(f"/_/api/chan/thread/?board=vg&num={n}")
            if status != 200:
                raise RuntimeError(f"thread {n}: HTTP {status}")
            got = select_posts(json.loads(body), n, have)
            tf.log(f"thread {n}: {len(got)} posts not in snapshots")
            recs += got
        db.close()
    recs = sorted(recs, key=lambda r: int(r["num"]))
    out.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in recs))
    return len(recs)


def rows(path: Path) -> list[dict[str, Any]]:
    """Supplement JSONL -> parquet-shaped dicts, ordered by post number."""
    res = []
    for line in path.read_text().splitlines():
        r = json.loads(line)
        m = r.get("media") or {}
        banned = m.get("banned") not in (None, "0", 0)
        res.append(
            {
                "post_num": int(r["num"]),
                "subnum": 0,
                "thread_num": int(r["thread_num"]),
                "is_op": r["op"] in ("1", 1, True),
                "timestamp": int(r["timestamp"]),
                "capcode": r["capcode"],
                "name": r["name"],
                "trip": r["trip"],
                "thread_title": r["title"],
                "comment": r["comment"],
                "media_filename": m.get("media_filename"),
                "media_w": m.get("media_w"),
                "media_h": m.get("media_h"),
                "media_size": m.get("media_size"),
                "media_hash": m.get("media_hash"),
                "media_spoiler": m.get("spoiler"),
                "deleted": r["deleted"],
                "_file_deleted": int(banned),
            }
        )
    return sorted(res, key=lambda d: d["post_num"])


def fetch_thumbs(path: Path, store: Path, interval: float = 1.0) -> dict[str, int]:
    """Fetch the supplement's own thumbnails (non-deleted posts, link present) into ``store``.

    Same client, spacing, STOP behaviour and md5-addressed layout as ``thumbs_fetch``; thumbs the
    store already holds are not requested again. Rows are recorded in the store's state DB.
    """
    if (store / "STOP").exists():
        raise RuntimeError(f"STOP file present in {store}")
    db = tf.open_state(store)
    client = tf.Client(store, db, interval)
    counts: dict[str, int] = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        m = r.get("media") or {}
        if r["deleted"] not in ("0", 0, None) or not m.get("thumb_link"):
            continue
        if m.get("banned") not in (None, "0", 0) or not m.get("media_hash"):
            continue
        md5 = tf.b64_to_hex(m["media_hash"])
        if md5 is None:
            continue
        no = int(r["num"])
        have = db.execute("SELECT status FROM thumb WHERE no=?", (no,)).fetchone()
        if have and have[0] in ("ok", "dup"):
            continue
        w = int(m["preview_w"]) if str(m.get("preview_w") or "").isdigit() else None
        h = int(m["preview_h"]) if str(m.get("preview_h") or "").isdigit() else None
        st, code, nbytes, note = tf.fetch_one(client, store, no, md5, m["thumb_link"], w, h)
        db.execute(
            "INSERT OR REPLACE INTO thumb (no, thread_no, md5, url, w, h, status, http, bytes, "
            "note, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (no, int(r["thread_num"]), md5, m["thumb_link"], w, h, st, code, nbytes, note,
             tf.now_iso()),
        )  # fmt: skip
        db.commit()
        counts[st] = counts.get(st, 0) + 1
    db.close()
    return counts
