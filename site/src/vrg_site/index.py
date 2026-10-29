"""Build the sharded search index, column files, text packs and lookups under ``out/data``.

Layout (all multi-byte ints little endian; every ``*.bin`` is gzip, sniffed by magic client-side):
  manifest.json
  idx/p<part>/<bucket>.bin   term shard: u32 hdrLen, hdr, postings
        hdr   = varint nTerms, then per term: varint len, utf8 bytes, varint df, varint postingsLen
        post  = per doc: varint(((doc - prev - 1) << 6) | (min(tf,3) - 1) << 4 | lenBucket)
                (prev starts at part.lo - 1)
  cols.bin                   N then four byte planes: thread idx lo, hi, flags, replies (saturated)
  days.bin                   u32 firstDoc per UTC day starting at manifest.day0 (+ sentinel N)
  threads.bin                JSON rows [no, edition, nPosts, nImages, first, last, subject]
  dom.bin                    link-domain doc lists
  q/<to_no % 256>.bin        reply lists: varint(dTo) varint(n) n x varint(dDoc)
  docs/pack<k>.bin           concatenated gzip blocks of BS docs; docs/blocks.bin = u32 offsets
  ../p/<no >> 19>.bin        permalink shards: varint(dNo) varint(threadIdx)
"""

from __future__ import annotations

import gzip
import json
import math
import struct
import time
from array import array
from collections import Counter
from pathlib import Path

import numpy as np

from . import corpus as C
from . import text, tok

BS = 64  # docs per text block
BUCKETS = 1024
PACK_BYTES = 16 * 1024 * 1024
STOP_FRAC = 0.20
MAX_REP = 255
FLAG_OP, FLAG_LINK, FLAG_GREEN, FLAG_SPOILER = 8, 16, 32, 64
EXT_CODE = {".jpg": 1, ".jpeg": 1, ".png": 2, ".gif": 3, ".webm": 4, ".mp4": 5}
PERM_SHIFT = 19
Q_BUCKETS = 256


def varint(n: int, out: bytearray) -> None:
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)


def gz(data: bytes, level: int = 9) -> bytes:
    return gzip.compress(data, level, mtime=0)


def write(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def build(
    cor: C.Corpus,
    quotes: list[tuple[int, int]],
    thumbs: dict[int, tuple[int, int, int, int, int]],
    data_dir: Path,
    perm_dir: Path,
    log=print,
) -> dict:
    t0 = time.time()
    posts = cor.posts
    n = len(posts)
    doc_of = {p[C.NO]: i for i, p in enumerate(posts)}
    stats: dict = {"docs": n}

    # ---- columns -----------------------------------------------------------------------
    rep = np.zeros(n, dtype=np.uint16)
    qsrc: dict[int, list[int]] = {}
    for a, b in quotes:
        d = doc_of[b]
        rep[d] += 1
        qsrc.setdefault(b, []).append(doc_of[a])
    thr = np.zeros(n, dtype=np.uint16)
    flags = np.zeros(n, dtype=np.uint8)
    times = np.zeros(n, dtype=np.int64)
    dom_docs: dict[str, list[int]] = {}
    live = cor.nos
    for i, p in enumerate(posts):
        thr[i] = cor.thread_idx[p[C.THREAD]]
        times[i] = p[C.TIME]
        f = 0
        ext = p[C.FEXT]
        if ext:
            f |= EXT_CODE.get(ext.lower(), 6)
        if p[C.NO] == p[C.THREAD]:
            f |= FLAG_OP
        body = p[C.BODY]
        if body:
            ds = text.domains(body)
            if ds:
                f |= FLAG_LINK
                for d in ds:
                    dom_docs.setdefault(d, []).append(i)
            if "\n>" in "\n" + body and any(
                ln.startswith(">") and not ln.startswith(">>") for ln in body.split("\n")
            ):
                f |= FLAG_GREEN
        if p[C.FSPOILER]:
            f |= FLAG_SPOILER
        flags[i] = f
    repb = np.minimum(rep, MAX_REP).astype(np.uint8)
    cols = (
        struct.pack("<I", n)
        + (thr & 0xFF).astype(np.uint8).tobytes()
        + (thr >> 8).astype(np.uint8).tobytes()
        + flags.tobytes()
        + repb.tobytes()
    )
    stats["cols_bytes"] = write(data_dir / "cols.bin", gz(cols))
    log(f"columns {time.time() - t0:.0f}s")

    # days table
    day = times // 86400
    day0 = int(day[0])
    ndays = int(day[-1]) - day0 + 1
    starts = np.searchsorted(day, np.arange(day0, day0 + ndays + 1), side="left").astype("<u4")
    stats["days_bytes"] = write(data_dir / "days.bin", gz(starts.tobytes()))

    # threads table
    trows = [
        [t.no, t.edition, t.n_posts, t.n_images, t.first_time, t.last_time, t.subject]
        for t in cor.threads
    ]
    stats["threads_bytes"] = write(
        data_dir / "threads.bin",
        gz(json.dumps(trows, ensure_ascii=False, separators=(",", ":")).encode()),
    )

    # domains
    dom_counts = Counter({d: len(v) for d, v in dom_docs.items()})
    top_dom = [d for d, c in dom_counts.most_common(64) if c >= 100]
    hdr = bytearray()
    body_b = bytearray()
    varint(len(top_dom), hdr)
    for d in top_dom:
        pl = bytearray()
        prev = -1
        for x in dom_docs[d]:
            varint(x - prev - 1, pl)
            prev = x
        db = d.encode()
        varint(len(db), hdr)
        hdr += db
        varint(len(dom_docs[d]), hdr)
        varint(len(pl), hdr)
        body_b += pl
    stats["dom_bytes"] = write(data_dir / "dom.bin", gz(struct.pack("<I", len(hdr)) + hdr + body_b))
    stats["domains"] = {d: dom_counts[d] for d in top_dom[:20]}

    # ---- quote shards --------------------------------------------------------------------
    qb: dict[int, list[int]] = {}
    for to_no in qsrc:
        qb.setdefault(to_no % Q_BUCKETS, []).append(to_no)
    qbytes = 0
    for k, tos in qb.items():
        out = bytearray()
        prev = 0
        for to_no in sorted(tos):
            srcs = sorted(qsrc[to_no])
            varint(to_no - prev, out)
            prev = to_no
            varint(len(srcs), out)
            pd = -1
            for s in srcs:
                varint(s - pd - 1, out)
                pd = s
        qbytes += write(data_dir / "q" / f"{k}.bin", gz(bytes(out)))
    stats["quote_bytes"] = qbytes

    # ---- permalink shards ------------------------------------------------------------------
    pb: dict[int, list[int]] = {}
    for i, p in enumerate(posts):
        pb.setdefault(p[C.NO] >> PERM_SHIFT, []).append(i)
    pbytes = 0
    for k, docs in pb.items():
        out = bytearray()
        prev = 0
        for i in sorted(docs, key=lambda d: posts[d][C.NO]):
            no = posts[i][C.NO]
            varint(no - prev, out)
            prev = no
            varint(int(thr[i]), out)
        pbytes += write(perm_dir / f"{k}.bin", gz(bytes(out)))
    stats["perm_bytes"] = pbytes
    stats["perm_files"] = len(pb)

    # ---- inverted index ------------------------------------------------------------------
    boundary = _boundary(cor)
    parts = [(0, boundary), (boundary, n)] if 0 < boundary < n else [(0, n)]
    df_all: Counter[str] = Counter()
    total_len = 0
    shard_bytes = 0
    nshards = 0
    npostings = 0
    for pi, (lo, hi) in enumerate(parts):
        buckets: list[dict[str, array]] = [{} for _ in range(BUCKETS)]
        fnv = tok.fnv1a16
        for i in range(lo, hi):
            p = posts[i]
            body = p[C.BODY]
            tks = tok.tokens(body) if body else []
            ln = len(tks)
            total_len += ln
            lb = min(15, int(math.log2(ln + 1) * 1.6))
            cnt: dict[str, int] = {}
            for t in tks:
                cnt[t] = cnt.get(t, 0) + 1
            if body and ">" in body:
                g = tok.greentext(body)
                if g:
                    for t in set(tok.tokens(g)):
                        cnt[tok.CH_GREEN + t] = 1
            nm = p[C.NAME]
            if nm and nm != "Anonymous":
                for t in set(tok.tokens(nm)):
                    cnt[tok.CH_NAME + t] = 1
            if p[C.TRIP]:
                cnt[tok.CH_TRIP + p[C.TRIP].lstrip("!").lower()] = 1
            if p[C.FNAME]:
                for t in set(tok.tokens(p[C.FNAME])):
                    cnt[tok.CH_FILE + t] = 1
            for t, tf in cnt.items():
                b = buckets[fnv(t) % BUCKETS]
                arr = b.get(t)
                if arr is None:
                    arr = b[t] = array("Q")
                arr.append((i << 6) | ((min(tf, 3) - 1) << 4) | lb)
            if pi == 0:
                for t in cnt:
                    if t[0] not in tok.MARKS:
                        df_all[t] += 1
        for bi, d in enumerate(buckets):
            if not d:
                continue
            ents = []
            body_b = bytearray()
            for t in sorted(d):
                arr = d[t]
                pl = bytearray()
                prev = lo - 1
                for v in arr:
                    doc = v >> 6
                    varint(((doc - prev - 1) << 6) | (v & 63), pl)
                    prev = doc
                ents.append((t.encode(), len(arr), len(pl)))
                body_b += pl
                npostings += len(arr)
            hdr = bytearray()
            varint(len(ents), hdr)
            for tb, df, pl_len in ents:
                varint(len(tb), hdr)
                hdr += tb
                varint(df, hdr)
                varint(pl_len, hdr)
            shard_bytes += write(
                data_dir / "idx" / f"p{pi}" / f"{bi}.bin",
                gz(struct.pack("<I", len(hdr)) + hdr + body_b),
            )
            nshards += 1
        del buckets
        log(f"index part {pi} [{lo},{hi}) {time.time() - t0:.0f}s")
    # stop list: computed from the history partition alone (88% of the corpus)
    hist_n = parts[0][1] - parts[0][0]
    stop = sorted(t for t, c in df_all.items() if c > STOP_FRAC * hist_n)
    stats.update(index_bytes=shard_bytes, shards=nshards, postings=npostings, stop=stop)
    log(f"index done {time.time() - t0:.0f}s")

    # ---- text blocks -----------------------------------------------------------------------
    packs: list[dict] = []
    cur = bytearray()
    offs: list[int] = []
    pack_first: list[int] = []
    blk = 0

    def flush() -> None:
        nonlocal cur
        if cur:
            k = len(packs)
            write(data_dir / "docs" / f"pack{k}.bin", bytes(cur))
            packs.append({"first": pack_first[-1], "size": len(cur)})
            cur = bytearray()

    for s in range(0, n, BS):
        rows = []
        for i in range(s, min(n, s + BS)):
            p = posts[i]
            row: list = [p[C.NO], p[C.TIME], text.mark_dead_quotes(p[C.BODY], live)]
            nm = p[C.NAME] if p[C.NAME] != "Anonymous" else None
            tr = p[C.TRIP] or None
            ext = p[C.FEXT]
            if ext:
                th = thumbs.get(p[C.NO])
                row += [
                    nm,
                    tr,
                    p[C.FNAME],
                    ext,
                    p[C.FW],
                    p[C.FH],
                    1 if p[C.FSPOILER] else 0,
                    list(th) if th and not p[C.FDELETED] else 0,
                ]
            elif nm or tr:
                row += [nm, tr]
            rows.append(row)
        z = gz(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode(), 6)
        if cur and len(cur) + len(z) > PACK_BYTES:
            flush()
        if not cur:
            pack_first.append(blk)
        offs.append(len(cur))
        cur += z
        blk += 1  # noqa: SIM113
    flush()
    stats["text_bytes"] = sum(p["size"] for p in packs)
    stats["blocks_bytes"] = write(
        data_dir / "docs" / "blocks.bin", gz(np.array(offs, "<u4").tobytes())
    )
    log(f"blocks done {time.time() - t0:.0f}s")

    manifest = {
        "v": 1,
        "N": n,
        "BS": BS,
        "B": BUCKETS,
        "parts": [[lo, hi] for lo, hi in parts],
        "packs": packs,
        "stop": stop,
        "avgdl": total_len / max(1, n),
        "day0": day0,
        "ndays": ndays,
        "nthreads": len(cor.threads),
        "perm_shift": PERM_SHIFT,
        "q_buckets": Q_BUCKETS,
        "snapshot": cor.snapshot,
        "domains": top_dom,
        "thumb_packs": 0,
    }
    write(data_dir / "manifest.json", json.dumps(manifest, separators=(",", ":")).encode())
    stats["build_s"] = time.time() - t0
    return stats


def _boundary(cor: C.Corpus) -> int:
    """First doc of the growing tail: the first live-era post (4chan API scraper)."""
    first_live = 520649835
    lo, hi = 0, len(cor.posts)
    while lo < hi:
        mid = (lo + hi) // 2
        if cor.posts[mid][C.NO] < first_live:
            lo = mid + 1
        else:
            hi = mid
    return lo
