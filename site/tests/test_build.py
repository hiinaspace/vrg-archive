"""End-to-end build on a tiny synthetic corpus: privacy rules are enforced in every output."""

import json
import sqlite3
import struct
from pathlib import Path

from vrg_site import build as B

SNAP = 1_800_000_000
DAY = 86400
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffc0000b08000a000c0100011100ffd9")


def make_corpus(path: Path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE post (no INTEGER PRIMARY KEY, thread_no INTEGER, time INTEGER, name TEXT, trip TEXT,
          capcode TEXT, sub TEXT, body TEXT, file_name TEXT, file_ext TEXT, file_w INTEGER, file_h INTEGER,
          file_size INTEGER, file_md5 TEXT, file_spoiler INTEGER, file_deleted INTEGER, deleted INTEGER, source TEXT);
        CREATE TABLE thread (no INTEGER PRIMARY KEY, subject TEXT, first_time INTEGER, last_time INTEGER,
          n_posts INTEGER, n_images INTEGER, prev_no INTEGER, next_no INTEGER, archived_on INTEGER);
        CREATE TABLE quote (from_no INTEGER, to_no INTEGER, cross_thread INTEGER, PRIMARY KEY (from_no, to_no));
        """
    )
    t0 = SNAP - 30 * DAY
    # thread 100 settled, 200 settled, 300 too recent
    for no, first, last in [
        (100, t0, t0 + DAY),
        (200, t0 + 2 * DAY, t0 + 3 * DAY),
        (300, SNAP - 2 * DAY, SNAP - DAY),
    ]:
        con.execute(
            "INSERT INTO thread VALUES (?,?,?,?,0,0,NULL,NULL,NULL)",
            (no, f"/vrg/ #{no}", first, last),
        )
    rows = [
        # no, thread, time, body, ext, fdel, deleted, spoiler, md5
        (100, 100, t0, "Hello quest world", ".png", 0, 0, 0, "aa"),
        (101, 100, t0 + 10, ">>100 greentext\n>implying secretword", None, 0, 0, 0, None),
        (102, 100, t0 + 20, "deleted post zzdeleted", None, 0, 1, 0, None),
        (103, 100, t0 + 30, ">>102 quoting a deleted post, >>200 cross", ".jpg", 1, 0, 0, "bb"),
        (104, 100, t0 + 40, "takedown target zztakedown", None, 0, 0, 0, None),
        (105, 100, t0 + 50, "image under md5 takedown", ".png", 0, 0, 1, "cc"),
        (200, 200, t0 + 2 * DAY, "second thread quest >>101", None, 0, 0, 0, None),
        (300, 300, SNAP - 2 * DAY, "too recent zzrecent", None, 0, 0, 0, None),
    ]
    for no, th, ts, body, ext, fdel, dele, sp, md5 in rows:
        con.execute(
            "INSERT INTO post VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                no,
                th,
                ts,
                "Anonymous",
                None,
                None,
                None,
                body,
                "fn" if ext else None,
                ext,
                10 if ext else None,
                12 if ext else None,
                99 if ext else None,
                md5,
                sp,
                fdel,
                dele,
                "t",
            ),
        )
    for f, t in [(101, 100), (103, 102), (103, 200), (200, 101)]:
        con.execute("INSERT INTO quote VALUES (?,?,0)", (f, t))
    con.commit()
    con.close()


def make_snapshot(path: Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE posts (no INTEGER PRIMARY KEY, thumbnail BLOB)")
    for no in (100, 103, 105):
        con.execute("INSERT INTO posts VALUES (?,?)", (no, JPEG))
    con.commit()
    con.close()


def grep(root: Path, needle: bytes) -> list[str]:
    return [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and needle in p.read_bytes()
    ]


def test_privacy_rules(tmp_path):
    db, snap, out = tmp_path / "c.sqlite", tmp_path / "s.sqlite", tmp_path / "dist"
    make_corpus(db)
    make_snapshot(snap)
    ex = tmp_path / "ex.txt"
    ex.write_text("# takedowns\n104\nmd5:cc\n")
    stats = B.build(db, snap, out, snapshot=SNAP, excluded=ex, skip_web=True, log=lambda *_: None)

    man = json.loads((out / "data/manifest.json").read_text())
    assert man["N"] == 5  # 100 101 103 105 200
    assert stats["corpus_stats"]["threads_unsettled_or_excluded"] == 1
    assert not (out / "t/300.html").exists()
    html = (out / "t/100.html").read_text()
    # deleted, excluded and unsettled posts appear nowhere, not even in unindexed text packs
    for needle in (b"zzdeleted", b"zztakedown", b"zzrecent"):
        assert grep(out / "t", needle) == []
        # text packs are gzip blocks; check the decoded blocks too
    import gzip

    pack = (out / "data/docs/pack0.bin").read_bytes()
    offs = __import__("numpy").frombuffer(
        gzip.decompress((out / "data/docs/blocks.bin").read_bytes()), "<u4"
    )
    blob = gzip.decompress(pack[offs[0] : offs[1] if len(offs) > 1 else None])
    assert b"zzdeleted" not in blob and b"zztakedown" not in blob and b"Hello quest world" in blob
    # a quote to a deleted post is plain text; cross-thread quote links to the other page
    assert 'href="#p102"' not in html and "&gt;&gt;102" in html
    assert 'href="200.html#p200"' in html
    assert 'id="p102"' not in html and 'id="p104"' not in html
    # backlinks: 101 quotes 100 and 200 quotes 101 (cross thread)
    assert 'Replies: <a class="ql" href="#p101">' in html
    # thumbnails: post 100 has one; 103 (file_deleted) and 105 (md5 takedown) have none
    assert 'data-t="0,' in html
    assert html.count('data-t="') == 1
    assert "fn.png" in html and "bb" not in html
    # md5 takedown removes even the file name of 105
    p105 = html[html.index('id="p105"') :]
    assert "File:" not in p105.split("</div></div>")[0]
    # permalink lookup: no 104 absent from its shard
    shard = gzip.decompress((out / f"p/{104 >> 19}.bin").read_bytes())
    nos, cur, i = [], 0, 0
    while i < len(shard):
        v = 0
        s = 0
        while True:
            c = shard[i]
            i += 1
            v |= (c & 127) << s
            s += 7
            if not c & 128:
                break
        cur += v
        nos.append(cur)
        while shard[i] & 128:
            i += 1
        i += 1
    assert 104 not in nos and 100 in nos
    thr = struct.unpack("<2I", (out / "p/threads.bin").read_bytes())
    assert thr == (100, 200)
    assert (out / "robots.txt").read_text().count("Disallow: /data/") == 1
    assert "TODO-contact" in (out / "about.html").read_text()
