"""End-to-end build on a tiny synthetic snapshot (schemas copied from the real sources)."""

import sqlite3
from pathlib import Path

import duckdb

from vrg_corpus import build
from vrg_corpus.normalize import CUTOFF

LIVE_SCHEMA = """
CREATE TABLE threads (op_id INTEGER PRIMARY KEY, subject TEXT, semantic_url TEXT,
  is_sticky INTEGER, is_closed INTEGER, is_archived INTEGER, archived_on INTEGER,
  first_seen INTEGER, last_modified_in_api INTEGER);
CREATE TABLE posts (no INTEGER PRIMARY KEY, thread_op_id INTEGER, resto INTEGER, time INTEGER,
  name TEXT, trip TEXT, capcode TEXT, sub TEXT, com TEXT, since4pass INTEGER, is_deleted INTEGER,
  tim INTEGER, filename TEXT, ext TEXT, fsize INTEGER, md5 TEXT, w INTEGER, h INTEGER,
  tn_w INTEGER, tn_h INTEGER, filedeleted INTEGER, spoiler INTEGER, custom_spoiler INTEGER,
  thumbnail BLOB);
"""
PQ_COLS = (
    "post_num, thread_num, thread_title, subnum, is_op, timestamp, timestamp_expired, capcode, "
    "email, name, trip, comment, poster_hash, poster_country, sticky, locked, deleted, "
    "media_filename, media_w, media_h, media_size, media_hash, media_link, thumb_link, "
    "media_spoiler"
)


def make_snapshot(d: Path) -> None:
    con = duckdb.connect()
    con.execute("create table t as select * from (values (0)) limit 0")  # placeholder
    con.execute(
        f"""create table p ({", ".join(f"{c.strip()} varchar" for c in PQ_COLS.split(","))})"""
    )
    c = CUTOFF
    rows = [
        # thread 1000000: old OP + reply quoting the OP and a cross-thread post
        (
            1000000,
            1000000,
            "/vrg/ - A &amp; B",
            None,
            1,
            1000,
            1100,
            None,
            None,
            "Anonymous",
            None,
            "hello<br>&gt;green",
            None,
            None,
            0,
            0,
            0,
            "a.JPG",
            10.0,
            20.0,
            30.0,
            "nhdlbXYagvu2uUHkom3x/w==",
            None,
            None,
            1,
        ),
        (
            1000001,
            1000000,
            None,
            None,
            0,
            1010,
            None,
            None,
            None,
            "Anonymous",
            None,
            '<a href="#p1000000" class="quotelink">&gt;&gt;1000000</a>',
            None,
            None,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        # thread c: OP in both sources, a reply only in parquet, a reply in both
        (
            c,
            c,
            "x",
            None,
            1,
            5000,
            None,
            None,
            None,
            "Anonymous",
            None,
            "op",
            None,
            None,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            c + 5,
            c,
            None,
            None,
            0,
            5005,
            None,
            None,
            None,
            "Anonymous",
            None,
            "gone",
            None,
            None,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            c + 9,
            c,
            None,
            0,
            0,
            5009,
            0,
            "N",
            None,
            "Anonymous",
            None,
            "plain\n>>1000001",
            None,
            None,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]
    for r in rows:
        con.execute(f"insert into p values ({','.join('?' * 25)})", list(map(_s, r)))
    con.execute("""create table q as select
      cast(post_num as bigint) post_num, cast(thread_num as bigint) thread_num, thread_title,
      cast(subnum as bigint) subnum, cast(is_op as bigint) is_op,
      cast(timestamp as bigint) timestamp,
      cast(timestamp_expired as bigint) timestamp_expired, capcode, email, name, trip, comment,
      poster_hash, poster_country, cast(sticky as bigint) sticky, cast(locked as bigint) locked,
      cast(deleted as bigint) deleted, media_filename, cast(media_w as double) media_w,
      cast(media_h as double) media_h, cast(media_size as double) media_size, media_hash,
      media_link, thumb_link, cast(media_spoiler as bigint) media_spoiler from p""")
    con.execute(f"copy q to '{d / build.PARQUET}' (format parquet)")
    db = sqlite3.connect(d / build.LIVE)
    db.executescript(LIVE_SCHEMA)
    db.execute("insert into threads values (?,?,?,0,0,1,0,0,0)", (c, "x", None))
    ins = (
        "insert into posts values (?,?,?,?,?,?,?,?,?,NULL,?,"
        "NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,0,0,NULL,NULL)"
    )
    db.execute(ins, (c, c, 0, 5000, "Anonymous", None, None, "x", "op", 0))
    db.execute(
        ins, (c + 9, c, c, 5009, "Anonymous", None, None, None, "plain<br>&gt;&gt;1000001", 1)
    )
    db.execute(
        ins, (c + 20, c, c, 5020, "Anonymous", None, None, None, "later &gt;&gt;" + str(c), 0)
    )
    db.commit()
    db.close()


def _s(v):
    return None if v is None else str(v)


def test_build_merge(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    make_snapshot(snap)
    out = tmp_path / "out"
    rep = build.build(snap, out)
    db = sqlite3.connect(out / "vrgarchive.sqlite")
    posts = {r[0]: r for r in db.execute("select no, body, deleted, source, sub from post")}
    assert sorted(posts) == [1000000, 1000001, CUTOFF, CUTOFF + 5, CUTOFF + 9, CUTOFF + 20]
    assert posts[1000000][1] == "hello\n>green" and posts[1000000][4] == "/vrg/ - A & B"
    assert posts[CUTOFF + 9][1:4] == ("plain\n>>1000001", 1, "live")  # live wins on overlap
    assert posts[CUTOFF + 5][2:4] == (1, "legacy")  # parquet-only inside live range: deleted
    assert rep["overlap"]["parquet_only_over_cutoff"] == [CUTOFF + 5]
    f = db.execute("select file_name, file_ext, file_md5 from post where no = 1000000").fetchone()
    assert f[0] == "a" and f[1] == ".jpg" and len(f[2]) == 32
    th = {r[0]: r for r in db.execute("select no, prev_no, next_no, n_posts, subject from thread")}
    assert th[1000000][1:3] == (None, CUTOFF) and th[CUTOFF][1:3] == (1000000, None)
    assert th[CUTOFF][3] == 4 and th[1000000][4] == "/vrg/ - A & B"
    q = set(db.execute("select from_no, to_no, cross_thread from quote"))
    assert q == {(1000001, 1000000, 0), (CUTOFF + 9, 1000001, 1), (CUTOFF + 20, CUTOFF, 0)}


def test_build_is_deterministic(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    make_snapshot(snap)
    build.build(snap, tmp_path / "a")
    build.build(snap, tmp_path / "b")
    assert (tmp_path / "a/vrgarchive.sqlite").read_bytes() == (
        tmp_path / "b/vrgarchive.sqlite"
    ).read_bytes()
