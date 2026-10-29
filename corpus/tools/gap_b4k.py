"""Count posts b4k has for the corpus gap days (read-only; adds nothing to the corpus).

usage: gap_b4k.py <corpus.sqlite> [interval=2.0]
For each gap run, thread-level API requests for the corpus threads that overlap the run, plus
any 'Previous thread >>N' chain target missing from the corpus. Counts b4k posts whose UTC
day is in the run and whose number is not already in the corpus.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from vrg_corpus.thumbs_fetch import Client, open_state

RUNS = [
    ("2022-08-03", "2022-08-04"),
    ("2025-04-15", "2025-04-24"),
    ("2025-05-10", "2025-05-10"),
    ("2025-05-16", "2025-05-17"),
    ("2026-06-27", "2026-06-30"),
    ("2026-09-03", "2026-09-06"),
    ("2026-10-21", "2026-10-21"),
]


def ts(day: str, end: bool = False) -> int:
    d = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return int(d.timestamp()) + (86400 if end else 0)


def main() -> None:
    corpus = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    store = Path("/tmp/vrg-gap-state")  # throwaway state for the client's event log
    cl = Client(store, open_state(store), interval)
    cache: dict[int, dict] = {}

    def thread(no: int) -> dict:
        if no not in cache:
            st, body = cl.get(f"/_/api/chan/thread/?board=vg&num={no}")
            j = json.loads(body) if st == 200 else {}
            t = j.get(str(no)) if isinstance(j, dict) else None
            cache[no] = t if isinstance(t, dict) else {}
        return cache[no]

    out = []
    for first, last in RUNS:
        a, b = ts(first), ts(last, True)
        cands = [
            r[0]
            for r in corpus.execute(
                "SELECT no FROM thread WHERE first_time < ? AND last_time >= ? ORDER BY no",
                (b + 2 * 86400, a - 2 * 86400),
            )
        ]
        # next thread after the run: follow 'Previous thread >>N' back while N is not in corpus
        nxt = corpus.execute(
            "SELECT no FROM thread WHERE first_time >= ? ORDER BY first_time LIMIT 1", (b,)
        ).fetchone()
        extra = []
        if nxt:
            cur = nxt[0]
            for _ in range(10):
                body = corpus.execute("SELECT body FROM post WHERE no=?", (cur,)).fetchone()
                m = re.search(r"Previous thread:?\s*>>(\d+)", body[0] if body else "")
                if not m:
                    break
                prev = int(m.group(1))
                if corpus.execute("SELECT 1 FROM thread WHERE no=?", (prev,)).fetchone():
                    break
                extra.append(prev)
                cur = prev
        total = imgs = 0
        threads_hit = []
        for tno in dict.fromkeys(cands + extra):
            t = thread(tno)
            posts = dict(t.get("posts") or {})
            if t.get("op"):
                posts[str(tno)] = t["op"]
            n = ni = 0
            for no, p in posts.items():
                if (
                    a <= int(p["timestamp"]) < b
                    and not corpus.execute("SELECT 1 FROM post WHERE no=?", (int(no),)).fetchone()
                ):
                    n += 1
                    m = p.get("media")
                    if isinstance(m, dict) and m.get("thumb_link") and p.get("deleted") == "0":
                        ni += 1
            if n:
                threads_hit.append((tno, n))
            total += n
            imgs += ni
        out.append((first, last, len(cands) + len(extra), total, imgs, threads_hit))
        print(
            first,
            last,
            "threads",
            len(cands) + len(extra),
            "b4k posts not in corpus",
            total,
            "with thumb",
            imgs,
            threads_hit,
            flush=True,
        )


if __name__ == "__main__":
    main()
