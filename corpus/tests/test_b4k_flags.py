"""b4k flags: thread selection, record trimming, resume markers, additive application in build."""

import json
import sqlite3

from test_b4k_supplement import MEDIA, api_post
from test_build import make_snapshot

from vrg_corpus import b4k_flags, build
from vrg_corpus.normalize import CUTOFF


def test_post_records_and_load(tmp_path):
    j = {
        "50": {
            "op": api_post(50, 50, op=1, media={**MEDIA, "spoiler": "1"}),
            "posts": {
                "51": api_post(51, 50, deleted="1"),
                "52": api_post(52, 50, media={**MEDIA, "banned": "1", "media_status": "banned"}),
            },
        }
    }
    recs = b4k_flags.post_records(j, 50)
    assert [(r["num"], r["spoiler"], r["deleted"], r["banned"]) for r in recs] == [
        (50, 1, 0, 0),
        (51, 0, 1, 0),
        (52, 0, 0, 1),
    ]
    assert b4k_flags.post_records(j, 99) is None
    path = tmp_path / "f.jsonl"
    marker = {"marker": 1, "thread": 50, "status": "ok", "n": 3}
    path.write_text("".join(json.dumps(r) + "\n" for r in [*recs, marker]))
    assert b4k_flags.done_threads(path) == {50}
    got = b4k_flags.load(path)
    assert got[50].spoiler and got[51].deleted and got[52].banned and not got[52].spoiler


def test_threads_from_corpus(tmp_path):
    p = tmp_path / "c.sqlite"
    db = sqlite3.connect(p)
    db.execute("create table post (no, thread_no, time, source)")
    db.executemany(
        "insert into post values (?,?,?,?)",
        [(1, 10, 2_000_000_000, "legacy"), (2, 20, 2_000_000_000, "live"), (3, 5, 100, "legacy")],
    )
    db.commit()
    db.close()
    assert b4k_flags.threads(p) == [10]


def test_build_applies_flags_additively(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    make_snapshot(snap)
    base = build.build(snap, tmp_path / "base")
    assert base["b4k_flags"] is None
    recs = [
        # legacy OP with file: spoiler + media banned; legacy reply: deleted; live post: ignored
        {"num": 1000000, "thread": 1000000, "spoiler": 1, "deleted": 0, "banned": 1},
        {"num": 1000001, "thread": 1000000, "spoiler": 0, "deleted": 1, "banned": 0},
        {"num": CUTOFF + 9, "thread": CUTOFF, "spoiler": 1, "deleted": 1, "banned": 1},
        {"marker": 1, "thread": 1000000, "status": "ok", "n": 2},
    ]
    (snap / b4k_flags.FILENAME).write_text("".join(json.dumps(r) + "\n" for r in recs))
    rep = build.build(snap, tmp_path / "fl")
    assert rep["b4k_flags"]["spoiler"] == 1
    assert rep["b4k_flags"]["deleted"] == 1
    assert rep["b4k_flags"]["file_deleted"] == 1
    q = "select no, file_spoiler, deleted, file_deleted from post order by no"
    a = {r[0]: r[1:] for r in sqlite3.connect(tmp_path / "base/vrgarchive.sqlite").execute(q)}
    b = {r[0]: r[1:] for r in sqlite3.connect(tmp_path / "fl/vrgarchive.sqlite").execute(q)}
    assert b[1000000] == (1, a[1000000][1], 1) and b[1000001][1] == 1
    assert {k: v for k, v in b.items() if k not in (1000000, 1000001)} == {
        k: v for k, v in a.items() if k not in (1000000, 1000001)
    }  # live row untouched; nothing else changed


def test_apply_flags_never_clears():
    from vrg_corpus.normalize import Post

    fl = {"spoiler": 0, "deleted": 0, "file_deleted": 0, "unmatched": 0}
    p = Post(*([None] * 16), 0, "legacy")._replace(deleted=1, file_deleted=1, file_name="x")
    q = build.apply_flags(p, b4k_flags.Flags(False, False, False), fl)
    assert q == p
