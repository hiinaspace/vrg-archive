"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vrg-corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="build the merged corpus SQLite")
    p.add_argument("snapdir", type=Path)
    p.add_argument("outdir", type=Path)
    p = sub.add_parser("gate", help="write gate.md")
    p.add_argument("snapdir", type=Path)
    p.add_argument("corpus", type=Path)
    p.add_argument("out", type=Path)
    p = sub.add_parser("thumbs", help="write thumbs.md")
    p.add_argument("snapdir", type=Path)
    p.add_argument("corpus", type=Path)
    p.add_argument("inventory", type=Path)
    p.add_argument("out", type=Path)
    p = sub.add_parser("probe", help="run/resume the b4k thumbnail probe")
    p.add_argument("snapdir", type=Path)
    p.add_argument("log", type=Path)
    p = sub.add_parser("probe-report", help="render the probe log as Markdown")
    p.add_argument("log", type=Path)
    p.add_argument("out", type=Path)

    p = sub.add_parser("thumbs-fetch", help="polite resumable fetch of b4k thumbnails")
    p.add_argument("corpus", type=Path)
    p.add_argument("--blob-db", type=Path, default=None, help="snapshot copy of the scraper DB")
    p.add_argument("--store", type=Path, default=None)
    p.add_argument("--interval", type=float, default=1.0, help="seconds between requests (>=0.5)")
    p.add_argument("--limit", type=int, default=None, help="stop after N thumbnail fetches")

    args = ap.parse_args(argv)
    if args.cmd == "build":
        import json

        from . import build

        rep = build.build(args.snapdir, args.outdir)
        print(json.dumps({k: v for k, v in rep.items() if k != "overlap"}, indent=1))
        ov = rep["overlap"]
        print("overlap:", ov["overlap_posts"], "identical:", ov["identical_rows"])
        return 0
    if args.cmd == "gate":
        from . import reports

        reports.gate(args.snapdir, args.corpus, args.out)
        return 0
    if args.cmd == "thumbs":
        from . import reports

        reports.thumbs(args.snapdir, args.corpus, args.inventory, args.out)
        return 0
    if args.cmd == "probe":
        from . import probe

        reason = probe.run(args.snapdir / "vrgarchive-2025-04-11.parquet", args.log)
        print("stopped:", reason or "complete")
        return 0
    if args.cmd == "probe-report":
        from . import probe

        args.out.write_text(probe.report(args.log))
        return 0
    if args.cmd == "thumbs-fetch":
        from . import thumbs_fetch as tf

        return tf.run(
            args.corpus,
            args.blob_db,
            args.store or tf.STORE_DEFAULT,
            args.interval,
            limit=args.limit,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
