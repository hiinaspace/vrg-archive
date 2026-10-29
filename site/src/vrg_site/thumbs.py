"""Pack the live-era 4chan thumbnail BLOBs into a few large Range-readable files."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
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


def pack(
    snapshot_db: Path, wanted: set[int], out_dir: Path
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
    return loc, {
        "thumbs": len(loc),
        "thumb_unique": len(seen),
        "thumb_bytes": unique_bytes,
        "thumb_packs": pack_i,
    }
