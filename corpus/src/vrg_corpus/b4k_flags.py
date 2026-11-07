"""Per-post spoiler / deletion flags for the legacy era, from b4k's thread API.

The parquet export has no usable spoiler or deletion flags for legacy rows. ``fetch`` asks b4k
for each legacy-era thread once (same polite client, spacing and STOP policy as
``thumbs_fetch``) and appends one JSONL record per post that carries a flag, plus one marker
line per finished thread, so a restart resumes where it stopped. ``load`` reads the file back as
``{post no: Flags}`` for ``build``, which only ever *adds* a flag.
"""

from __future__ import annotations

import json
import signal
import sqlite3
import time
from pathlib import Path
from typing import Any, NamedTuple

from . import thumbs_fetch as tf

FILENAME = "b4k-flags.jsonl"


class Flags(NamedTuple):
    spoiler: bool
    deleted: bool
    banned: bool  # media banned/removed on b4k


def _set(v: Any) -> bool:
    return v not in (None, "0", 0, "", False)


def threads(corpus: Path, since: int = tf.SINCE_DEFAULT) -> list[int]:
    """Threads holding legacy-source posts in b4k's era, newest first."""
    con = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    out = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT thread_no FROM post WHERE source='legacy' AND time >= ? "
            "ORDER BY thread_no DESC",
            (since,),
        )
    ]
    con.close()
    return out


def post_records(thread_json: Any, thread_no: int) -> list[dict[str, Any]] | None:
    """All posts of one API thread response, trimmed to the flag fields; None if not found."""
    t = thread_json.get(str(thread_no)) if isinstance(thread_json, dict) else None
    if not isinstance(t, dict):
        return None
    posts = dict(t.get("posts") or {})
    if t.get("op"):
        posts[str(thread_no)] = t["op"]
    out = []
    for p in posts.values():
        if str(p.get("subnum") or "0") != "0":
            continue
        m = p.get("media") if isinstance(p.get("media"), dict) else {}
        out.append(
            {
                "num": int(p["num"]),
                "thread": thread_no,
                "deleted": int(_set(p.get("deleted"))),
                "spoiler": int(_set(m.get("spoiler"))),
                "banned": int(_set(m.get("banned"))),
                "media_status": m.get("media_status"),
                "has_media": int(bool(m)),
            }
        )
    return sorted(out, key=lambda r: r["num"])


def done_threads(path: Path) -> set[int]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if "marker" in r:
                done.add(int(r["thread"]))
    return done


def fetch(corpus: Path, out: Path, store: Path, interval: float = 1.0, limit: int | None = None):
    """Run or resume. Returns 0 complete, 3 stopped by policy, 2 on SIGTERM/limit."""
    if (store / "STOP").exists():
        tf.log(f"STOP file present: {(store / 'STOP').read_text().strip()}")
        return 3
    db = tf.open_state(store)
    client = tf.Client(store, db, interval)
    signal.signal(signal.SIGTERM, lambda *_: setattr(client, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(client, "stopping", True))
    todo = threads(corpus)
    done = done_threads(out)
    tf.log(f"b4k-flags: {len(todo)} threads, {len(done)} already done; interval {client.interval}s")
    n = 0
    last = time.monotonic()
    try:
        with out.open("a") as f:
            for no in todo:
                if no in done:
                    continue
                status, body = client.get(f"/_/api/chan/thread/?board=vg&num={no}")
                if status == 0:
                    raise tf.Stop(f"thread {no}: no response")
                recs: list[dict[str, Any]] | None = None
                mstatus = f"http{status}"
                if status == 200:
                    try:
                        recs = post_records(json.loads(body), no)
                        mstatus = "ok" if recs is not None else "notfound"
                    except json.JSONDecodeError:
                        mstatus = "badjson"
                lines = [json.dumps(r, sort_keys=True) for r in recs or []]
                lines.append(
                    json.dumps(
                        {"marker": 1, "thread": no, "status": mstatus, "n": len(recs or [])},
                        sort_keys=True,
                    )
                )
                f.write("\n".join(lines) + "\n")
                f.flush()
                n += 1
                if time.monotonic() - last > 600:
                    last = time.monotonic()
                    tf.log(f"b4k-flags: {n + len(done)}/{len(todo)} threads; {client.requests} req")
                if limit and n >= limit:
                    raise tf.Stop(f"--limit {limit} reached")
        tf.log("b4k-flags: complete")
        return 0
    except tf.Stop as e:
        tf.log(f"stopping: {e}")
        return 3 if (store / "STOP").exists() else 2
    finally:
        db.close()


def load(path: Path) -> dict[int, Flags]:
    """{post no: Flags} for posts b4k returned. Threads b4k did not have contribute nothing."""
    res: dict[int, Flags] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "marker" in r:
            continue
        res[int(r["num"])] = Flags(bool(r["spoiler"]), bool(r["deleted"]), bool(r["banned"]))
    return res
