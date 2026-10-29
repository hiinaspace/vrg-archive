"""Pack the live-era 4chan thumbnail BLOBs into a few large Range-readable files."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import struct
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACK_BYTES = 16 * 1024 * 1024


def jpeg_size(b: bytes) -> tuple[int, int]:
    """(width, height) from the first SOFn marker; (0, 0) if the stream is odd."""
    i = 2
    n = len(b)
    while i + 9 < n:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        (seglen,) = struct.unpack(">H", b[i + 2 : i + 4])
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", b[i + 5 : i + 9])
            return w, h
        i += 2 + seglen
    return 0, 0


def pool_md5s(state_db: Path) -> set[str]:
    """md5s that the b4k fetcher has stored (read from a local copy of its state DB)."""
    with tempfile.TemporaryDirectory() as d:
        local = Path(d) / "state.sqlite"
        shutil.copy(state_db, local)
        con = sqlite3.connect(f"file:{local}?mode=ro", uri=True)
        got = {r[0] for r in con.execute("SELECT md5 FROM thumb WHERE status IN ('ok','dup')")}
        con.close()
    return got


def pack(
    snapshot_db: Path,
    wanted: set[int],
    out_dir: Path,
    pool_dir: Path | None = None,
    pool_md5: dict[int, str] | None = None,
    pool_have: set[str] | None = None,
) -> tuple[dict[int, tuple[int, int, int, int, int]], dict[str, int]]:
    """Write ``out_dir/pack<k>.bin``; return {post no: (pack, offset, length, w, h)}.

    Only posts in ``wanted`` (published, file not deleted) get a thumbnail. Identical blobs
    (reposts) are stored once.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{snapshot_db}?mode=ro", uri=True)
    loc: dict[int, tuple[int, int, int, int, int]] = {}
    seen: dict[bytes, tuple[int, int, int, int, int]] = {}
    pack_i = 0
    cur = bytearray()
    unique_bytes = 0

    def flush() -> None:
        nonlocal cur, pack_i
        if cur:
            (out_dir / f"pack{pack_i}.bin").write_bytes(cur)
            pack_i += 1
            cur = bytearray()

    for no, blob in con.execute(
        "SELECT no, thumbnail FROM posts WHERE thumbnail IS NOT NULL ORDER BY no"
    ):
        if no not in wanted:
            continue
        key = hashlib.sha1(blob).digest()
        hit = seen.get(key)
        if hit is not None:
            # the pack the original lives in may already be flushed; reuse its location
            loc[no] = hit
            continue
        if len(cur) + len(blob) > PACK_BYTES:
            flush()
        w, h = jpeg_size(blob)
        ent = (pack_i, len(cur), len(blob), w, h)
        cur += blob
        unique_bytes += len(blob)
        seen[key] = ent
        loc[no] = ent
    flush()
    con.close()
    blob_posts = len(loc)
    if pool_dir is not None and pool_md5 and pool_have:
        # b4k thumbnails stored by md5: post order (thread locality), each md5 once
        todo = sorted(n for n in wanted if n not in loc and pool_md5.get(n) in pool_have)
        by_md5: dict[str, tuple[int, int, int, int, int]] = {}
        order = list(dict.fromkeys(pool_md5[n] for n in todo))

        def read(m: str) -> bytes:
            return (pool_dir / "raw" / m[:2] / f"{m}.jpg").read_bytes()

        with ThreadPoolExecutor(16) as ex:
            for lo in range(0, len(order), 2000):
                chunk = order[lo : lo + 2000]
                for m, blob in zip(chunk, ex.map(read, chunk), strict=True):
                    if len(cur) + len(blob) > PACK_BYTES:
                        flush()
                    w, h = jpeg_size(blob)
                    by_md5[m] = (pack_i, len(cur), len(blob), w, h)
                    cur += blob
                    unique_bytes += len(blob)
        flush()
        for n in todo:
            loc[n] = by_md5[pool_md5[n]]
        seen.update({m.encode(): e for m, e in by_md5.items()})
        pool_posts = len(todo)
    else:
        pool_posts = 0
    return loc, {
        "thumb_blob_posts": blob_posts,
        "thumb_pool_posts": pool_posts,
        "thumbs": len(loc),
        "thumb_unique": len(seen),
        "thumb_bytes": unique_bytes,
        "thumb_packs": pack_i,
    }
