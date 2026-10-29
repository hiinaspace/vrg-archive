"""Build the merged, normalized corpus SQLite from the two source snapshots."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb

from . import normalize
from .normalize import CUTOFF, POST_COLS, Counters, Post

PARQUET = "vrgarchive-2025-04-11.parquet"
LIVE = "vrgscraper-archive.sqlite"

SCHEMA = """
CREATE TABLE post (
  no INTEGER PRIMARY KEY,
  thread_no INTEGER NOT NULL,
  time INTEGER NOT NULL,
  name TEXT NOT NULL,
  trip TEXT,
  capcode TEXT,
  sub TEXT,
  body TEXT NOT NULL,
  file_name TEXT,
  file_ext TEXT,
  file_w INTEGER,
  file_h INTEGER,
  file_size INTEGER,
  file_md5 TEXT,
  file_spoiler INTEGER,
  file_deleted INTEGER NOT NULL,
  deleted INTEGER NOT NULL,
  source TEXT NOT NULL
);
CREATE TABLE thread (
  no INTEGER PRIMARY KEY,
  subject TEXT,
  first_time INTEGER NOT NULL,
  last_time INTEGER NOT NULL,
  n_posts INTEGER NOT NULL,
  n_images INTEGER NOT NULL,
  prev_no INTEGER,
  next_no INTEGER,
  archived_on INTEGER
);
CREATE TABLE quote (
  from_no INTEGER NOT NULL,
  to_no INTEGER NOT NULL,
  cross_thread INTEGER,
  PRIMARY KEY (from_no, to_no)
) WITHOUT ROWID;
"""

INDEXES = """
CREATE INDEX post_thread ON post(thread_no, no);
CREATE INDEX post_time ON post(time);
CREATE INDEX post_md5 ON post(file_md5) WHERE file_md5 IS NOT NULL;
CREATE INDEX quote_to ON quote(to_no, from_no);
CREATE INDEX thread_first ON thread(first_time);
"""

_INSERT = f"INSERT INTO post ({','.join(POST_COLS)}) VALUES ({','.join('?' * len(POST_COLS))})"


def _parquet_rows(path: Path, batch: int = 50000):
    con = duckdb.connect()
    cur = con.execute(f"select * from read_parquet('{path}') order by post_num")
    cols = [d[0] for d in cur.description]
    while True:
        rows = cur.fetchmany(batch)
        if not rows:
            return
        for r in rows:
            yield dict(zip(cols, r, strict=True))


def _live_dicts(db: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(sql)]


def compare_overlap(pq: dict[int, Post], live: dict[int, Post]) -> dict[str, Any]:
    """Field-by-field comparison of the posts present in both sources."""
    nos = sorted(set(pq) & set(live))
    ident_rows = 0
    per_field: Counter[str] = Counter()
    examples: dict[str, list] = {f: [] for f in POST_COLS}
    for no in nos:
        a, b = pq[no], live[no]
        same = True
        for f in POST_COLS:
            if getattr(a, f) != getattr(b, f):
                per_field[f] += 1
                same = False
                if len(examples[f]) < 10:
                    examples[f].append({"no": no, "parquet": getattr(a, f), "live": getattr(b, f)})
        ident_rows += same
    return {
        "overlap_posts": len(nos),
        "identical_rows": ident_rows,
        "differing_rows": len(nos) - ident_rows,
        "differing_by_field": dict(per_field),
        "examples": {k: v for k, v in examples.items() if v},
        "parquet_only_over_cutoff": sorted(set(pq) - set(live)),
        "live_only_below_cutoff": sorted(n for n in live if n < CUTOFF),
    }


def build(snapdir: Path, outdir: Path) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / "vrgarchive.sqlite"
    tmp = outdir / "vrgarchive.sqlite.tmp"
    for p in (tmp, Path(str(tmp) + "-journal")):
        p.unlink(missing_ok=True)
    c = Counters()

    live_db = sqlite3.connect(f"file:{snapdir / LIVE}?mode=ro", uri=True)
    live_rows = _live_dicts(live_db, "select * from posts order by no")
    live_threads = _live_dicts(live_db, "select * from threads order by op_id")
    live_db.close()
    live: dict[int, Post] = {}
    for r in live_rows:
        live[int(r["no"])] = normalize.from_live(r, c)
    del live_rows

    db = sqlite3.connect(tmp)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    thread_subject: dict[int, str | None] = {}
    thread_title_any: dict[int, str] = {}
    thread_archived: dict[int, int] = {}
    pq_overlap: dict[int, Post] = {}
    pq_rows_total = 0
    pq_inserted = 0
    quotes: list[tuple[int, int]] = []
    buf: list[Post] = []

    def flush() -> None:
        nonlocal buf
        db.executemany(_INSERT, buf)
        buf = []

    def add(p: Post) -> None:
        buf.append(p)
        for t in normalize.quotes(p.body):
            quotes.append((p.no, t))
        if len(buf) >= 50000:
            flush()

    for r in _parquet_rows(snapdir / PARQUET):
        pq_rows_total += 1
        c.rows["parquet"] += 1
        p = normalize.from_parquet(r, c)
        if p is None:
            continue
        if r["is_op"]:
            thread_subject[p.thread_no] = p.sub
            te = r["timestamp_expired"]
            if te:
                thread_archived[p.thread_no] = int(te)
        elif r["thread_title"] and p.thread_no not in thread_title_any:
            title = normalize.text_field(r["thread_title"], r["subnum"] is None)
            if title:
                thread_title_any[p.thread_no] = title
        if p.no >= CUTOFF:
            pq_overlap[p.no] = p
            if p.no in live:
                continue  # live DB wins on overlap
            # Inside the live scrape's coverage but absent from it: the post was gone from 4chan
            # when the scraper first fetched the thread, so it was deleted. legacy rows carry no
            # deleted flag of their own, so infer it.
            p = p._replace(deleted=1)
        add(p)
        pq_inserted += 1
    for no in sorted(live):
        c.rows["live"] += 1
        add(live[no])
    flush()

    # thread subjects / archive times from the live threads table (live wins for >= CUTOFF)
    for t in live_threads:
        op = live.get(int(t["op_id"]))
        is_html = op is not None and op.source == "live"
        subj = normalize.text_field(t["subject"], is_html)
        thread_subject[int(t["op_id"])] = (
            subj if subj is not None else thread_subject.get(int(t["op_id"]))
        )
        if t["archived_on"]:
            thread_archived[int(t["op_id"])] = int(t["archived_on"])
        else:
            thread_archived.pop(int(t["op_id"]), None)

    db.executemany("INSERT INTO quote(from_no,to_no) VALUES (?,?)", quotes)
    db.execute(
        "UPDATE quote SET cross_thread = (SELECT (a.thread_no <> b.thread_no) FROM post a, post b "
        "WHERE a.no = quote.from_no AND b.no = quote.to_no)"
    )
    db.execute(
        "INSERT INTO thread(no,first_time,last_time,n_posts,n_images) "
        "SELECT thread_no, MIN(time), MAX(time), COUNT(*), COUNT(file_name) FROM post "
        "GROUP BY thread_no"
    )
    upd = []
    for (no,) in db.execute("SELECT no FROM thread").fetchall():
        subj = thread_subject.get(no) or thread_title_any.get(no)
        upd.append((subj, thread_archived.get(no), no))
    db.executemany("UPDATE thread SET subject=?, archived_on=? WHERE no=?", upd)
    order = [r[0] for r in db.execute("SELECT no FROM thread ORDER BY first_time, no")]
    links = [
        (order[i - 1] if i else None, order[i + 1] if i + 1 < len(order) else None, n)
        for i, n in enumerate(order)
    ]
    db.executemany("UPDATE thread SET prev_no=?, next_no=? WHERE no=?", links)
    db.executescript(INDEXES)
    db.commit()
    db.execute("VACUUM")
    db.close()
    tmp.replace(dest)

    cmp = compare_overlap(pq_overlap, live)
    report = {
        "parquet_rows": pq_rows_total,
        "parquet_rows_inserted": pq_inserted,
        "live_rows": len(live),
        "live_backfill_rows_with_html": c.rows["backfill_html"],
        "ghost_posts_skipped": c.ghosts,
        "bad_md5": c.bad_md5,
        "empty_name_defaulted": c.empty_name,
        "ext_mismatch": c.ext_mismatch,
        "unknown_capcodes": dict(c.capcode_unknown),
        "html_known_tags": dict(c.html.tags),
        "html_dropped_decoration": dict(c.html.dropped),
        "html_unknown_tags": dict(c.html.unknown),
        "html_unknown_examples": c.html.unknown_examples,
        "overlap": cmp,
    }
    (outdir / "build-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return report
