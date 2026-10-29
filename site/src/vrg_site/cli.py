from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import build as B

DATA = Path("/home/s/code/vrg-archive-data")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="vrg-site")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the whole site")
    b.add_argument("--corpus", type=Path, default=DATA / "corpus-20261029/vrgarchive.sqlite")
    b.add_argument(
        "--snapshot-db", type=Path, default=DATA / "snap-20261029/vrgscraper-archive.sqlite"
    )
    b.add_argument("--out", type=Path, default=DATA / "site-r1/dist")
    b.add_argument("--snapshot", type=int, default=B.SNAPSHOT_DEFAULT)
    b.add_argument("--excluded", type=Path, default=None)
    b.add_argument("--limit-threads", type=int, default=None, help="dev: only the newest N threads")
    b.add_argument("--skip-web", action="store_true")
    b.add_argument("--pool", type=Path, default=None, help="b4k thumbnail store (md5-addressed)")
    a = ap.parse_args(argv)
    stats = B.build(
        a.corpus, a.snapshot_db, a.out, a.snapshot, a.excluded, a.limit_threads, a.skip_web, a.pool
    )
    print(json.dumps({k: v for k, v in stats.items() if k != "stop"}, indent=1, default=str))
