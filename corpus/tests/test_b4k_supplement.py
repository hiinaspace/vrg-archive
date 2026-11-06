"""b4k supplement: selection, normalization, priority and determinism in the build."""

import json
import sqlite3

from test_build import make_snapshot

from vrg_corpus import b4k_supplement, build
from vrg_corpus.normalize import CUTOFF, Counters, from_b4k


def api_post(num, thread, op=0, deleted="0", media=None, comment="hi", title=None):
    return {
        "num": str(num),
        "subnum": "0",
        "thread_num": str(thread),
        "op": str(op),
        "timestamp": 2000 + num % 1000,
        "capcode": "N",
        "name": "Anonymous",
        "trip": None,
        "title": title,
        "comment": comment,
        "deleted": deleted,
        "media": media,
        "comment_processed": "ignored",
    }


MEDIA = {
    "media_filename": "pic.png",
    "media_w": "757",
    "media_h": "665",
    "media_size": "557258",
    "media_hash": "bqWREYngrGE48WPtYhFKVA==",
    "spoiler": "0",
    "banned": "0",
    "media_status": "normal",
    "thumb_link": "https://arch.b4k.dev/media/vg/thumb/1/2/3s.jpg",
    "preview_w": "125",
    "preview_h": "109",
    "extra": "dropped",
}


def test_select_posts_filters_known_and_trims():
    j = {
        "50": {
            "op": api_post(50, 50, op=1, title="T"),
            "posts": {
                "51": api_post(51, 50),
                "52": api_post(52, 50, media=MEDIA, deleted="1"),
            },
        }
    }
    got = b4k_supplement.select_posts(j, 50, {50, 51})
    assert [r["num"] for r in got] == ["52"]
    assert "comment_processed" not in got[0] and "extra" not in got[0]["media"]
    assert got[0]["deleted"] == "1"


def test_from_b4k_flags():
    rec = {**api_post(52, 50, media={**MEDIA, "banned": "1"}, deleted="1")}
    (row,) = _rows([rec])
    p = from_b4k(row, Counters())
    assert p.source == "b4k" and p.deleted == 1 and p.file_deleted == 1
    assert (p.file_name, p.file_ext, p.file_w, p.file_size) == ("pic", ".png", 757, 557258)
    assert len(p.file_md5) == 32


def _rows(recs, tmp=None):
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp())
    f = d / "s.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return b4k_supplement.rows(f)


def test_build_with_supplement(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    make_snapshot(snap)
    base = build.build(snap, tmp_path / "base")
    recs = [
        api_post(1000001, 1000000, comment="dup of parquet; must lose"),
        api_post(CUTOFF + 9, CUTOFF, comment="dup of live; must lose"),
        api_post(1000002, 1000000, media=MEDIA, comment=">>1000000 new"),
        api_post(1000003, 1000000, deleted="1"),
    ]
    (snap / b4k_supplement.FILENAME).write_text("".join(json.dumps(r) + "\n" for r in recs))
    rep = build.build(snap, tmp_path / "sup")
    assert rep["b4k_supplement_rows"] == 4 and rep["b4k_supplement_inserted"] == 2
    db = sqlite3.connect(tmp_path / "sup/vrgarchive.sqlite")
    rows = {r[0]: r[1:] for r in db.execute("select no, source, deleted, body from post")}
    assert rows[1000002] == ("b4k", 0, ">>1000000 new")
    assert rows[1000003][:2] == ("b4k", 1)
    assert rows[1000001][0] != "b4k" and rows[CUTOFF + 9][0] == "live"
    n = db.execute("select n_posts from thread where no=1000000").fetchone()[0]
    b = sqlite3.connect(tmp_path / "base/vrgarchive.sqlite")
    assert n == b.execute("select n_posts from thread where no=1000000").fetchone()[0] + 2
    assert base["parquet_rows_inserted"] == rep["parquet_rows_inserted"]
    # deterministic, and absent file = old two-source build
    build.build(snap, tmp_path / "sup2")
    assert (tmp_path / "sup/vrgarchive.sqlite").read_bytes() == (
        tmp_path / "sup2/vrgarchive.sqlite"
    ).read_bytes()
