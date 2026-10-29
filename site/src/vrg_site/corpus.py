"""Load the published subset of the R0 corpus: settled threads, no deleted posts, no takedowns."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

SETTLE_DAYS = 7

# row layout of the post tuples
NO, THREAD, TIME, NAME, TRIP, BODY, FNAME, FEXT, FW, FH, FSIZE, FSPOILER, FDELETED, MD5 = range(14)

_POST_SQL = """
SELECT no, thread_no, time, name, trip, body, file_name, file_ext, file_w, file_h,
       file_size, file_spoiler, file_deleted, file_md5
FROM post WHERE deleted = 0 ORDER BY time, no
"""


@dataclass
class Exclusions:
    posts: set[int] = field(default_factory=set)
    threads: set[int] = field(default_factory=set)
    md5: set[str] = field(default_factory=set)


def read_exclusions(path: Path | None) -> Exclusions:
    """excluded_ids.txt: one entry per line. ``123`` = post, ``thread:123``, ``md5:<hex>``."""
    ex = Exclusions()
    if path is None or not path.exists():
        return ex
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if line.startswith("thread:"):
            ex.threads.add(int(line[7:]))
        elif line.startswith("md5:"):
            ex.md5.add(line[4:].strip())
        elif line.isdigit():
            ex.posts.add(int(line))
        else:
            raise ValueError(f"unparseable line in excluded ids: {raw!r}")
    return ex


@dataclass
class Thread:
    no: int
    subject: str
    edition: int  # 0 when the subject has no '#N'
    first_time: int
    last_time: int
    n_posts: int = 0
    n_images: int = 0


@dataclass
class Corpus:
    threads: list[Thread]  # ordered by first_time
    thread_idx: dict[int, int]  # thread no -> index
    posts: list[tuple]  # ordered by (time, no); only published posts
    nos: set[int]  # published post numbers
    snapshot: int
    stats: dict[str, int]


def load(db: Path, snapshot: int, excluded: Exclusions, limit_threads: int | None = None) -> Corpus:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cutoff = snapshot - SETTLE_DAYS * 86400
    stats: dict[str, int] = {}
    trows = con.execute(
        "SELECT no, subject, first_time, last_time FROM thread ORDER BY first_time, no"
    ).fetchall()
    stats["threads_total"] = len(trows)
    keep = [t for t in trows if t[3] < cutoff and t[0] not in excluded.threads]
    stats["threads_unsettled_or_excluded"] = len(trows) - len(keep)
    if limit_threads:
        keep = keep[-limit_threads:]
    threads = []
    for no, subject, first, last in keep:
        m = re.search(r"#(\d+)", subject or "")
        threads.append(Thread(no, subject or f"Thread {no}", int(m[1]) if m else 0, first, last))
    thread_idx = {t.no: i for i, t in enumerate(threads)}
    posts: list[tuple] = []
    nos: set[int] = set()
    skipped_excl = 0
    for row in con.execute(_POST_SQL):
        no: int = row[NO]
        ti = thread_idx.get(row[THREAD])
        if ti is None:
            continue
        if no in excluded.posts:
            skipped_excl += 1
            continue
        if row[MD5] and row[MD5].lower() in excluded.md5:
            # takedown of an image: keep the text, drop every trace of the file
            row = (*row[:FNAME], None, None, None, None, None, 0, 0, row[MD5])
        posts.append(row)
        nos.add(no)
        t = threads[ti]
        t.n_posts += 1
        if row[FEXT]:
            t.n_images += 1
    empty = [t for t in threads if t.n_posts == 0]
    if empty:  # every post deleted or excluded: no page, no table row
        threads = [t for t in threads if t.n_posts > 0]
        thread_idx = {t.no: i for i, t in enumerate(threads)}
    stats["threads_empty_dropped"] = len(empty)
    stats["posts_published"] = len(posts)
    stats["posts_excluded_by_list"] = skipped_excl
    con.close()
    return Corpus(threads, thread_idx, posts, nos, snapshot, stats)


def load_quotes(db: Path, corpus: Corpus) -> list[tuple[int, int]]:
    """(from_no, to_no) pairs where both ends are published."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    nos = corpus.nos
    out = [
        (a, b) for a, b in con.execute("SELECT from_no, to_no FROM quote") if a in nos and b in nos
    ]
    con.close()
    return out
