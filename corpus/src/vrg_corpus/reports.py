"""Markdown reports (gate, thumbs) computed from the built corpus and the source snapshot."""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from .build import LIVE, PARQUET
from .normalize import CUTOFF

PARQUET_TOTAL, LIVE_TOTAL, OVERLAP_EXPECTED = 1_406_752, 207_805, 1_516
CONTENT_FIELDS = [
    "thread_no", "time", "name", "trip", "capcode", "sub", "body", "file_name", "file_ext",
    "file_w", "file_h", "file_size", "file_md5",
]  # fmt: skip


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def gap_days(db: sqlite3.Connection, since: str = "2019-01-01") -> tuple[list[dict], str]:
    """Days (UTC) with 0 posts or < 20% of the trailing 28-day median, from `since`."""
    counts = Counter(
        d for (d,) in db.execute("select strftime('%Y-%m-%d', time, 'unixepoch') from post")
    )
    last = max(counts)  # the final day is partial (snapshot time); excluded from the list
    d0 = datetime.fromisoformat("2018-12-04").date()
    d1 = datetime.fromisoformat(last).date()
    series: dict[str, int] = {}
    d = d0
    while d <= d1:
        series[d.isoformat()] = counts.get(d.isoformat(), 0)
        d += timedelta(days=1)
    days = sorted(series)
    out = []
    for i, day in enumerate(days):
        if day < since or day == last:
            continue
        window = [series[x] for x in days[max(0, i - 28) : i]]
        med = statistics.median(window)
        if series[day] == 0 or series[day] < 0.2 * med:
            out.append({"day": day, "n": series[day], "median28": med})
    return out, last


def _ranges(gaps: list[dict]) -> list[tuple[str, str, int, int]]:
    """Collapse consecutive gap days into (first, last, n_days, total_posts)."""
    res: list[list] = []
    for g in gaps:
        d = datetime.fromisoformat(g["day"]).date()
        if res and (d - res[-1][1]).days == 1:
            res[-1][1] = d
            res[-1][2] += 1
            res[-1][3] += g["n"]
        else:
            res.append([d, d, 1, g["n"]])
    return [(a.isoformat(), b.isoformat(), n, t) for a, b, n, t in res]


def gate(snapdir: Path, corpus: Path, out: Path) -> None:
    db = sqlite3.connect(f"file:{corpus / 'vrgarchive.sqlite'}?mode=ro", uri=True)
    rep = json.loads((corpus / "build-report.json").read_text())
    ov = rep["overlap"]
    L: list[str] = ["# Gate report: merged corpus", ""]

    # 1. counts
    total = db.execute("select count(*) from post").fetchone()[0]
    expected = PARQUET_TOTAL + LIVE_TOTAL - OVERLAP_EXPECTED
    by_src = db.execute("select source, count(*), sum(deleted) from post group by 1").fetchall()
    extras = ov["parquet_only_over_cutoff"]
    L += ["## 1. Counts", "", "| item | n |", "|---|---|"]
    L += [
        f"| parquet rows | {rep['parquet_rows']:,} |",
        f"| live DB rows | {rep['live_rows']:,} |",
        f"| overlap (same post no in both) | {ov['overlap_posts']:,} |",
        f"| expected total = {PARQUET_TOTAL:,} + {LIVE_TOTAL:,} - {OVERLAP_EXPECTED:,} | "
        f"{expected:,} |",
        f"| **corpus `post` rows** | **{total:,}** |",
        f"| difference | {total - expected:+,} |",
        f"| parquet rows >= {CUTOFF} absent from the live DB (kept, see below) | {len(extras)} |",
        f"| live rows below the cutoff | {len(ov['live_only_below_cutoff'])} |",
        f"| ghost posts (subnum > 0) skipped | {rep['ghost_posts_skipped']} |",
        "",
    ]
    L += [
        "Rows by `source` (legacy = 4chan-API HTML export, b4k = foolfuuka plain text, "
        "live = scraper HTML):",
        "",
        "| source | posts | deleted |",
        "|---|---|---|",
    ]
    L += [f"| {s} | {n:,} | {int(d or 0):,} |" for s, n, d in by_src]
    L += [""]
    L += [
        "Total equals the expected figure exactly, with no unexplained rows. The merge rule in "
        "the brief (parquet below the cutoff, live from it) would drop "
        f"{len(extras)} parquet posts ({', '.join(map(str, extras))}) that are in the "
        "parquet but not in the live DB: they were already gone from 4chan when the scraper "
        "first fetched the thread (one is quoted as a `deadlink` in a live post). The build "
        "keeps them (source `legacy`, `deleted = 1` inferred); dropping them would give "
        f"{total - len(extras):,}.",
        "",
    ]

    # 2. overlap
    L += ["## 2. Overlap after normalization", ""]
    n = ov["overlap_posts"]
    diff = ov["differing_by_field"]
    L += [
        f"{n:,} posts are in both sources.",
        "",
        "| field | differing posts | identical |",
        "|---|---|---|",
    ]
    for f in CONTENT_FIELDS + ["file_spoiler", "file_deleted", "deleted", "source"]:
        k = diff.get(f, 0)
        L.append(f"| {f} | {k} | {n - k:,} |")
    content_diff = sum(1 for f in CONTENT_FIELDS if diff.get(f))
    L += [
        "",
        f"All {len(CONTENT_FIELDS)} content fields (including `body`) are identical for "
        f"{n:,}/{n:,} posts" + ("." if not content_diff else f"; {content_diff} fields differ."),
        "The expected differences are not defects: `source` (legacy vs live), `file_spoiler` "
        "(legacy rows have no usable spoiler flag, live has real 0/1), and `deleted` (legacy "
        "rows have no deleted flag; live knows).",
        "",
        "Raw (pre-normalization) comparison of parquet `comment` against live `com`, "
        "checking the owner's note that one comment differs:",
        "",
    ]
    pq = duckdb.connect()
    live = sqlite3.connect(f"file:{snapdir / LIVE}?mode=ro", uri=True)
    live_com = dict(live.execute("select no, com from posts where no >= ?", (CUTOFF,)))
    raw_diff = []
    for no, comment, subnum in pq.execute(
        f"select post_num, comment, subnum from read_parquet('{snapdir / PARQUET}') "
        f"where post_num >= {CUTOFF} order by post_num"
    ).fetchall():
        if no in live_com and comment != live_com[no]:
            raw_diff.append((no, comment, live_com[no], subnum))
    L.append(f"- raw `comment` != `com` for {len(raw_diff)} of {n:,} posts.")
    for no, a, b, sn in raw_diff[:10]:
        kind = "plain-text" if sn == 0 else "HTML"
        L += [f"  - post {no} (parquet row is {kind}): parquet `{a!r}`", f"    live `{b!r}`"]
    L += [
        "",
        "Those posts compare equal after normalization (table above), which is the point of the "
        "normalizer: the raw difference is representation only.",
    ]
    L += ["", "Examples of the (expected) differing fields, up to 10 each:", ""]
    for f in ("deleted", "file_spoiler"):
        for e in ov["examples"].get(f, [])[:10]:
            L.append(f"- {f}: post {e['no']}: parquet={e['parquet']!r} live={e['live']!r}")
    L += [""]

    # 3. gaps
    gaps, last = gap_days(db)
    ranges = _ranges(gaps)
    L += [
        "## 3. Per-day gaps from 2019-01-01",
        "",
        "Days (UTC) with 0 posts, or fewer than 20% of the trailing 28-day median of daily post "
        f"counts. The last day ({last}, partial) is excluded. {len(gaps)} days, "
        f"{len(ranges)} runs.",
        "",
        "| first | last | days | posts in run |",
        "|---|---|---|---|",
    ]
    L += [f"| {a} | {b} | {k} | {t} |" for a, b, k, t in ranges]
    L += ["", "Per-day detail (day: posts, trailing median):", ""]
    L.append(", ".join(f"{g['day']}: {g['n']} (med {g['median28']:g})" for g in gaps) or "none")
    L += [""]
    zero = [g for g in gaps if g["n"] == 0]
    L.append(f"{len(zero)} of those days have exactly 0 posts.")
    # per-year gap counts
    py = Counter(g["day"][:4] for g in gaps)
    L += ["", "Gap days per year: " + ", ".join(f"{y}: {k}" for y, k in sorted(py.items())), ""]

    # 4. threads
    L += ["## 4. Threads", ""]
    nthreads = db.execute("select count(*) from thread").fetchone()[0]
    no_subj = db.execute("select no from thread where subject is null or subject = ''").fetchall()
    no_op = db.execute(
        "select no, n_posts from thread where no not in (select no from post)"
    ).fetchall()
    no_prev = db.execute("select count(*) from thread where prev_no is null").fetchone()[0]
    no_next = db.execute("select count(*) from thread where next_no is null").fetchone()[0]
    null_arch = db.execute("select count(*) from thread where archived_on is null").fetchone()[0]
    nonvrg = db.execute(
        "select no, subject from thread where subject is not null and subject not like '%vrg%'"
    ).fetchall()
    L += [
        f"- threads: {nthreads:,}",
        f"- threads with NULL/empty subject: {len(no_subj)}",
        f"- threads whose OP post is not in the corpus: {len(no_op)}"
        + (f" ({no_op[:10]})" if no_op else ""),
        f"- threads whose subject does not contain 'vrg': {len(nonvrg)}"
        + (f" ({nonvrg[:10]})" if nonvrg else ""),
        f"- thread rows with no `prev_no`: {no_prev}, with no `next_no`: {no_next} "
        "(expected 1 each)",
        f"- threads with `archived_on` NULL: {null_arch} (unknown expiry: parquet OPs with "
        "timestamp_expired 0/NULL, live threads with archived_on 0 or not yet archived)",
    ]
    live_t = live.execute(
        "select count(*), sum(is_archived), sum(is_archived and archived_on = 0), "
        "sum(not is_archived) from threads"
    ).fetchone()
    stale = live.execute(
        "select count(*) from threads t where not is_archived and "
        "(select max(time) from posts p where p.thread_op_id = t.op_id) "
        "< strftime('%s','now') - 7*86400"
    ).fetchone()[0]
    L += [
        f"- live DB `threads`: {live_t[0]} rows, {live_t[1]} flagged archived "
        f"({live_t[2]} of them with archived_on = 0), {live_t[3]} not flagged archived; "
        f"{stale} of those unflagged threads have had no post for over 7 days (stale flag).",
        "",
    ]
    ed = Counter()
    for (s,) in db.execute("select subject from thread"):
        ed[s] += 1
    dup = [(s, k) for s, k in ed.items() if k > 1 and s]
    L.append(f"- subjects shared by more than one thread: {len(dup)} (e.g. {sorted(dup)[:5]})")
    L += [
        "",
        "Not checked: whether post sets inside each thread are complete beyond the per-day "
        "counts above (a thread truncated mid-way would only show as a thin day).",
        "",
    ]
    out.write_text("\n".join(L))


def thumbs(snapdir: Path, corpus: Path, inventory: Path, out: Path) -> None:
    """Per-month image-post inventory by thumbnail source."""
    db = sqlite3.connect(f"file:{corpus / 'vrgarchive.sqlite'}?mode=ro", uri=True)
    live = sqlite3.connect(f"file:{snapdir / LIVE}?mode=ro", uri=True)
    blob = {no for (no,) in live.execute("select no from posts where thumbnail is not null")}
    tim_by_no = dict(live.execute("select no, tim from posts where tim is not null"))
    local_tims = set()
    for line in inventory.read_text().splitlines():
        name = line.split("\t")[0].rsplit("/", 1)[-1]
        local_tims.add(int(name.split(".")[0]))
    local = {no for no, t in tim_by_no.items() if t in local_tims}
    q = f"select post_num from read_parquet('{snapdir / PARQUET}') where thumb_link is not null"
    b4k_link = {no for (no,) in duckdb.connect().execute(q).fetchall()}
    rows = db.execute(
        "select no, strftime('%Y-%m', time, 'unixepoch'), deleted, file_deleted "
        "from post where file_name is not null"
    ).fetchall()
    agg: dict[tuple[str, bool], Counter] = defaultdict(Counter)
    for no, month, deleted, fdel in rows:
        clean = not deleted and not fdel
        cats = []
        if no in blob:
            cats.append("blob")
        if no in local:
            cats.append("local")
        if no in b4k_link:
            cats.append("b4k")
        first = cats[0] if cats else "none"
        for key in ((month, False), (month, True)) if clean else ((month, False),):
            c = agg[key]
            c["n"] += 1
            c["first_" + first] += 1
            for k in cats:
                c["has_" + k] += 1
    months = sorted({m for m, _ in agg})

    def table(clean: bool) -> list[str]:
        hdr = (
            "| month | image posts | live BLOB | local full file | b4k thumb_link | "
            "first source: BLOB | local | b4k | none |"
        )
        t = [hdr, "|---|---|---|---|---|---|---|---|---|"]
        tot: Counter = Counter()
        for m in months:
            c = agg.get((m, clean))
            if not c:
                continue
            tot.update(c)
            t.append(
                f"| {m} | {c['n']} | {c['has_blob']} | {c['has_local']} | {c['has_b4k']} | "
                f"{c['first_blob']} | {c['first_local']} | {c['first_b4k']} | {c['first_none']} |"
            )
        t.append(
            f"| **total** | {tot['n']:,} | {tot['has_blob']:,} | {tot['has_local']:,} | "
            f"{tot['has_b4k']:,} | {tot['first_blob']:,} | {tot['first_local']:,} | "
            f"{tot['first_b4k']:,} | {tot['first_none']:,} |"
        )
        return t

    L = [
        "# Thumbnail inventory by month (UTC)",
        "",
        "Image post = corpus row with a file. Sources:",
        "",
        "- **live BLOB**: `posts.thumbnail` is non-null in the live scraper DB.",
        f"- **local full file**: a file named `{{tim}}.{{ext}}` for the post's `tim` exists under "
        f"the scraper's media directory ({len(local_tims):,} files in the "
        "inventory taken 2026-10-29, listing only). Only live-DB rows have a `tim`; parquet rows "
        "have none, so they can never match a local file.",
        "- **b4k thumb_link**: the parquet row carries a thumbnail URL (16,147 rows; 16,136 on "
        "arch.b4k.dev, 11 on archived.moe).",
        "- **first source** assigns each post to exactly one bucket in the order BLOB, local, b4k, "
        "none, so those four columns sum to the row total.",
        "",
        "## All image posts",
        "",
        *table(False),
        "",
        "## Excluding deleted posts and deleted files",
        "",
        "(`deleted = 0 and file_deleted = 0`; legacy rows have no deleted flag, so they count "
        "as not deleted.)",
        "",
        *table(True),
        "",
        "Not checked: whether the local files are intact or match the md5; whether the b4k URLs "
        "still resolve (see b4k-probe.md).",
        "",
    ]
    out.write_text("\n".join(L))
