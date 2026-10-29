# Gate report: merged corpus

## 1. Counts

| item | n |
|---|---|
| parquet rows | 1,406,752 |
| live DB rows | 207,805 |
| overlap (same post no in both) | 1,516 |
| expected total = 1,406,752 + 207,805 - 1,516 | 1,613,041 |
| **corpus `post` rows** | **1,613,041** |
| difference | +0 |
| parquet rows >= 520649835 absent from the live DB (kept, see below) | 4 |
| live rows below the cutoff | 0 |
| ghost posts (subnum > 0) skipped | 0 |

Rows by `source` (legacy = 4chan-API HTML export, b4k = foolfuuka plain text, live = scraper HTML):

| source | posts | deleted |
|---|---|---|
| b4k | 113,945 | 23,845 |
| legacy | 1,339,838 | 3 |
| live | 159,258 | 1,113 |

Total equals the expected figure exactly, with no unexplained rows. The merge rule in the brief (parquet below the cutoff, live from it) would drop 4 parquet posts (520649895, 520650428, 520719309, 520721272) that are in the parquet but not in the live DB: they were already gone from 4chan when the scraper first fetched the thread (one is quoted as a `deadlink` in a live post). The build keeps them (source `legacy`, `deleted = 1` inferred); dropping them would give 1,613,037.

## 2. Overlap after normalization

1,516 posts are in both sources.

| field | differing posts | identical |
|---|---|---|
| thread_no | 0 | 1,516 |
| time | 0 | 1,516 |
| name | 0 | 1,516 |
| trip | 0 | 1,516 |
| capcode | 0 | 1,516 |
| sub | 0 | 1,516 |
| body | 0 | 1,516 |
| file_name | 0 | 1,516 |
| file_ext | 0 | 1,516 |
| file_w | 0 | 1,516 |
| file_h | 0 | 1,516 |
| file_size | 0 | 1,516 |
| file_md5 | 0 | 1,516 |
| file_spoiler | 417 | 1,099 |
| file_deleted | 0 | 1,516 |
| deleted | 3 | 1,513 |
| source | 1516 | 0 |

All 13 content fields (including `body`) are identical for 1,516/1,516 posts.
The expected differences are not defects: `source` (legacy vs live), `file_spoiler` (legacy rows have no usable spoiler flag, live has real 0/1), and `deleted` (legacy rows have no deleted flag; live knows).

Raw (pre-normalization) comparison of parquet `comment` against live `com`, checking the owner's note that one comment differs:

- raw `comment` != `com` for 1 of 1,516 posts.
  - post 520750268 (parquet row is plain-text): parquet `'>>520748786\nyou good, bro?\nwhere are the pics?'`
    live `'<a href="#p520748786" class="quotelink">&gt;&gt;520748786</a><br>you good, bro?<br>where are the pics?'`

Those posts compare equal after normalization (table above), which is the point of the normalizer: the raw difference is representation only.

Examples of the (expected) differing fields, up to 10 each:

- deleted: post 520744235: parquet=0 live=1
- deleted: post 520852303: parquet=0 live=1
- deleted: post 521020574: parquet=0 live=1
- file_spoiler: post 520649835: parquet=None live=0
- file_spoiler: post 520649986: parquet=None live=0
- file_spoiler: post 520650168: parquet=None live=0
- file_spoiler: post 520650298: parquet=None live=0
- file_spoiler: post 520650353: parquet=None live=0
- file_spoiler: post 520651802: parquet=None live=0
- file_spoiler: post 520651923: parquet=None live=0
- file_spoiler: post 520653554: parquet=None live=0
- file_spoiler: post 520658656: parquet=None live=0
- file_spoiler: post 520659007: parquet=None live=0

## 3. Per-day gaps from 2019-01-01

Days (UTC) with 0 posts, or fewer than 20% of the trailing 28-day median of daily post counts. The last day (2026-10-29, partial) is excluded. 24 days, 7 runs.

| first | last | days | posts in run |
|---|---|---|---|
| 2022-08-03 | 2022-08-04 | 2 | 261 |
| 2025-04-15 | 2025-04-24 | 10 | 55 |
| 2025-05-10 | 2025-05-10 | 1 | 0 |
| 2025-05-16 | 2025-05-17 | 2 | 32 |
| 2026-06-27 | 2026-06-30 | 4 | 32 |
| 2026-09-03 | 2026-09-06 | 4 | 78 |
| 2026-10-21 | 2026-10-21 | 1 | 90 |

Per-day detail (day: posts, trailing median):

2022-08-03: 130 (med 690.5), 2022-08-04: 131 (med 690.5), 2025-04-15: 55 (med 333), 2025-04-16: 0 (med 333), 2025-04-17: 0 (med 333), 2025-04-18: 0 (med 294), 2025-04-19: 0 (med 277), 2025-04-20: 0 (med 265.5), 2025-04-21: 0 (med 253), 2025-04-22: 0 (med 253), 2025-04-23: 0 (med 243.5), 2025-04-24: 0 (med 243.5), 2025-05-10: 0 (med 148.5), 2025-05-16: 0 (med 164.5), 2025-05-17: 32 (med 164.5), 2026-06-27: 32 (med 451), 2026-06-28: 0 (med 451), 2026-06-29: 0 (med 451), 2026-06-30: 0 (med 451), 2026-09-03: 78 (med 533), 2026-09-04: 0 (med 533), 2026-09-05: 0 (med 533), 2026-09-06: 0 (med 533), 2026-10-21: 90 (med 639.5)

17 of those days have exactly 0 posts.

Gap days per year: 2022: 2, 2025: 13, 2026: 9

## 4. Threads

- threads: 2,250
- threads with NULL/empty subject: 0
- threads whose OP post is not in the corpus: 0
- threads whose subject does not contain 'vrg': 0
- thread rows with no `prev_no`: 1, with no `next_no`: 1 (expected 1 each)
- threads with `archived_on` NULL: 417 (unknown expiry: parquet OPs with timestamp_expired 0/NULL, live threads with archived_on 0 or not yet archived)
- live DB `threads`: 276 rows, 168 flagged archived (149 of them with archived_on = 0), 108 not flagged archived; 102 of those unflagged threads have had no post for over 7 days (stale flag).

- subjects shared by more than one thread: 165 (e.g. [('/vrg/', 2), ('/vrg/ - Virtual Reality General', 19), ('/vrg/ - Virtual Reality General #1004', 2), ('/vrg/ - Virtual Reality General #1015', 2), ('/vrg/ - Virtual Reality General #1043', 2)])

Not checked: whether post sets inside each thread are complete beyond the per-day counts above (a thread truncated mid-way would only show as a thin day).
