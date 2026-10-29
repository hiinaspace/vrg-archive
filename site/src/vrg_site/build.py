"""Orchestrate a full site build: data files, thread pages, static pages, web bundle."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from . import corpus as C
from . import index, threads, thumbs

SITE_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_DEFAULT = 1793306940  # snap-20261029: .backup finished 2026-10-29 14:49 MDT


def build(
    corpus_db: Path,
    snapshot_db: Path,
    out: Path,
    snapshot: int = SNAPSHOT_DEFAULT,
    excluded: Path | None = None,
    limit_threads: int | None = None,
    skip_web: bool = False,
    pool: Path | None = None,
    log=print,
) -> dict:
    t0 = time.time()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ex = C.read_exclusions(excluded if excluded is not None else SITE_DIR / "excluded_ids.txt")
    cor = C.load(corpus_db, snapshot, ex, limit_threads)
    quotes = C.load_quotes(corpus_db, cor)
    log(
        f"loaded {len(cor.posts)} posts, {len(cor.threads)} threads, {len(quotes)} quotes "
        f"{time.time() - t0:.0f}s"
    )
    wanted = {p[C.NO] for p in cor.posts if p[C.FEXT] and not p[C.FDELETED]}
    pool_dir = pool_md5 = pool_have = None
    if pool is not None and (pool / "state.sqlite").exists():
        pool_dir = pool
        pool_have = thumbs.pool_md5s(pool / "state.sqlite")
        pool_md5 = {p[C.NO]: p[C.MD5] for p in cor.posts if p[C.NO] in wanted and p[C.MD5]}
    loc, tstats = thumbs.pack(
        snapshot_db, wanted, out / "data" / "thumbs", pool_dir, pool_md5, pool_have
    )
    log(f"thumbs {tstats} {time.time() - t0:.0f}s")
    stats = index.build(cor, quotes, loc, out / "data", out / "p", log=log)
    stats.update(tstats)
    # manifest patch: thumbnail pack count
    mpath = out / "data" / "manifest.json"
    man = json.loads(mpath.read_text())
    man["thumb_packs"] = tstats["thumb_packs"]
    mpath.write_text(json.dumps(man, separators=(",", ":")))
    # permalink thread table (raw u32)
    (out / "p" / "threads.bin").write_bytes(
        struct.pack(f"<{len(cor.threads)}I", *[t.no for t in cor.threads])
    )
    shift = index.PERM_SHIFT
    (out / "p" / "index.html").write_text(
        (SITE_DIR / "static" / "permalink.html").read_text().replace("__SHIFT__", str(shift))
    )
    stats.update(threads.render_all(cor, quotes, loc, out / "t", log=log))
    # static files
    for name in ("thread.css", "thread.js"):
        shutil.copy(SITE_DIR / "static" / name, out / "t" / name)
    for name in ("robots.txt", "_headers", "NOTICE.txt"):
        shutil.copy(SITE_DIR / "static" / name, out / name)
    fmt = lambda ts: datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")  # noqa: E731
    about = (SITE_DIR / "static" / "about.html").read_text()
    for k, v in {
        "__POSTS__": f"{len(cor.posts):,}",
        "__THREADS__": f"{len(cor.threads):,}",
        "__FIRST__": fmt(cor.posts[0][C.TIME]),
        "__LAST__": fmt(cor.posts[-1][C.TIME]),
        "__SNAP__": fmt(snapshot),
    }.items():
        about = about.replace(k, v)
    (out / "about.html").write_text(about)
    urls = "".join(f"<url><loc>{threads.SITE}/t/{t.no}.html</loc></url>" for t in cor.threads)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{threads.SITE}/t/</loc></url>{urls}</urlset>'
    )
    if not skip_web:
        subprocess.run(["node", "build.mjs", "--out", str(out)], cwd=SITE_DIR / "web", check=True)
    stats["corpus_stats"] = cor.stats
    stats["total_s"] = time.time() - t0
    files = [f for f in out.rglob("*") if f.is_file()]
    stats["dist_files"] = len(files)
    stats["dist_bytes"] = sum(f.stat().st_size for f in files)
    stats["max_file_bytes"] = max(f.stat().st_size for f in files)
    (out.parent / "build-report.json").write_text(json.dumps(stats, indent=1, default=str))
    return stats
