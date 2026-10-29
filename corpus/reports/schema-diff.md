# Schema diff: parquet export vs live scraper DB

Snapshot `snap-20261029`. Numbers are from queries on the snapshot and from `build-report.json`.

## 0. The two big surprises in one place

1. **The parquet is two different encodings, not one.** Only 65,399 of its 1,406,752 rows
   (`subnum = 0`, `capcode = 'N'`, 2019-08 to 2025-04) are foolfuuka plain text. The other
   1,341,353 rows (`subnum IS NULL`) are **raw 4chan API HTML**: `<br>`, `&gt;`, `&#039;`,
   `<span class="quote">`, `<a class="quotelink">`, `<wbr>`, `<s>`. The "plain text" claim holds for
   only 4.6% of the rows. The normalizer therefore needs the HTML converter for both sources.
2. **The live DB is two encodings as well.** Its `capcode = 'N'` rows (48,547) were written by
   `vrg_scraper.backfill` from b4k and are plain text; `capcode IS NULL` rows (159,258) come from the
   4chan API and are HTML. 187 of the `N` rows (all in posts 566488916..566566237, May 2026) hold
   raw 4chan HTML anyway (b4k returned HTML for that range). The normalizer decides per row for
   `N` rows (`<br>`, `</a>`, `</span>`, `<wbr>`, `&gt;`, `&#039;`, `&quot;` mean HTML).

The two sources agree exactly where they overlap (1,516 posts, all 13 content fields identical
after normalization; see gate.md). Timestamps need no timezone adjustment: parquet and live agree
to the second. A monotonicity check of `timestamp` against `post_num` over all 1.4M parquet rows
finds only a handful of inversions larger than 10 minutes (2 per source kind, none forming a
4-5 hour offset block), so the foolfuuka local-time shift is absent from this export.

## 1. Column mapping

`post` columns are the corpus names. "legacy" = parquet rows with `subnum IS NULL`,
"b4k" = parquet `subnum = 0` rows and live `capcode = 'N'` rows, "live" = live `capcode IS NULL`.

### Parquet (25 columns)

| parquet column | corpus | notes |
|---|---|---|
| `post_num` | `post.no` | unique over all 1,406,752 rows |
| `thread_num` | `post.thread_no` | OP rows satisfy `post_num = thread_num`; no violations either way |
| `thread_title` | `post.sub` (OP rows), `thread.subject` | legacy: filled on OP rows only (1,896 of 1,976 OPs; the other 80 OPs are b4k rows). b4k rows: filled on every row. One thread (280556819) has two distinct titles over its rows; the OP row's title wins. Legacy titles are HTML-escaped (`#728&gt;`), unescaped |
| `subnum` | (drives `source`) | NULL on 1,341,353 rows, 0 on 65,399, never > 0. **No ghost posts exist**, so nothing is dropped; the build counts and skips `subnum > 0` if it ever appears |
| `is_op` | (`post.no = thread_no`) | 1,976 OPs = 1,976 threads |
| `timestamp` | `post.time` | unix seconds, real UTC |
| `timestamp_expired` | `thread.archived_on` for OPs; not kept for replies | see section 3 |
| `capcode` | `post.capcode` | 'N' (65,399, = foolfuuka "normal") -> NULL; 'mod' (2 rows) kept; NULL on legacy. Letters M/A/D/V/F/G would map to 4chan words (none present) |
| `email` | dropped | 0 non-null values |
| `name` | `post.name` | legacy is HTML-escaped (`I have no idea what I&#039;m doing.`), unescaped. 25 rows are NULL/empty, defaulted to `Anonymous`. 1,403,199 rows are literally `Anonymous` |
| `trip` | `post.trip` | 1,445 non-null, forms `!abc` and `!!abc`; same in live (58 rows) |
| `comment` | `post.body` | legacy: HTML -> text. b4k: kept verbatim. 31,213 NULL (image-only posts), stored as empty string |
| `poster_hash`, `poster_country` | dropped | 0 non-null (/vg/ has neither) |
| `sticky` | dropped | 0 on every row, including OPs that were stickied; unusable |
| `locked` | dropped | 1 on 1,793 legacy OPs only |
| `deleted` | `post.deleted` | b4k rows: real (21,882 = 1; 6,262 of them have files). **Legacy rows: always 0, i.e. unknown**, not "not deleted" |
| `media_filename` | `post.file_name` + `post.file_ext` | always `name.ext` (all 325,544 have a dot); split on the last dot, ext lowercased with the dot. Legacy is HTML-escaped |
| `media_w`, `media_h`, `media_size` | `file_w`, `file_h`, `file_size` | stored as DOUBLE, cast to INTEGER |
| `media_hash` | `file_md5` | base64 of the 16-byte md5, 24 chars with `==`. Converted to 32-char lowercase hex; 0 invalid |
| `media_link` | dropped | non-null on 16,136 rows only (arch-img.b4k.dev full image) |
| `thumb_link` | not in `post` (thumbs.md / probe) | 16,147 rows, all b4k-sourced: 16,136 `arch.b4k.dev/media/vg/thumb/...`, 11 `archived.moe/files/vg/thumb/...` (the brief said arch.b4k.dev only) |
| `media_spoiler` | `post.file_spoiler` (b4k rows only) | **legacy: 1 on all 1,896 legacy OPs, NULL on every other legacy row** (307,507 image posts). That is the 4chan OP-only `custom_spoiler` count mislabeled, not a spoiler flag. Ignored for legacy (stored NULL = unknown). b4k rows: 65,215 zeros, 184 ones |

There is **no `tim`** (4chan's server filename) in the parquet, so no parquet post can be matched to
a file in `vrgscraper-media`.

### Live `posts` (24 columns)

| live column | corpus | notes |
|---|---|---|
| `no`, `thread_op_id`, `resto` | `no`, `thread_no` | `resto = 0` for OPs; 276 OPs = 276 threads; no mismatches. `resto` is not kept |
| `time` | `time` | unix seconds |
| `name` | `name` | HTML rows are escaped, unescaped. 207,577 `Anonymous`. b4k rows: backfill writes `name or ""`, none are empty here |
| `trip` | `trip` | 58 rows |
| `capcode` | `capcode`, `source` | the real 4chan values (mod, admin, ...) would appear here but none do; the only non-NULL value is the **backfill marker 'N'** (48,547), not a capcode |
| `sub` | `sub` (OP only) | 276 non-null = OPs. HTML-escaped on `live` rows |
| `com` | `body` | HTML or plain; 3,321 NULL (image-only) -> '' |
| `since4pass` | dropped | 3 non-null |
| `is_deleted` | `deleted` | 3,077 = 1 (1,113 from 4chan-API rows, i.e. "vanished from the thread JSON"; 1,964 from b4k's own `deleted` flag). 962 of them have a file |
| `tim` | (local-media join key) | 51,226 non-null. Recovered by backfill from b4k's `media_orig`/`exif` for `N` rows |
| `filename` | `file_name` | 4chan form (no ext, HTML-escaped: `3 years of Haruhi&#039;s shit`). Backfill stores the stem of b4k's `media_filename`, plain. Both give a bare name matching the parquet split |
| `ext` | `file_ext` | with leading dot (`.png`); lowercase in the data. Parquet has no ext column; derived |
| `fsize`, `w`, `h` | `file_size`, `file_w`, `file_h` | ints, full-size dimensions |
| `md5` | `file_md5` | base64 (24 chars), same encoding as parquet; converted to hex |
| `tn_w`, `tn_h` | dropped | thumbnail dimensions |
| `filedeleted` | `file_deleted` | 20 rows. Parquet has no equivalent (all 0 = unknown) |
| `spoiler` | `file_spoiler` | 0/1. Defaulted to 0 (not NULL) by the scraper when the API omits it |
| `custom_spoiler` | dropped | **Not a spoiler flag.** 214 rows carry 1, all OPs with `spoiler = 0`; it is the 4chan OP-only "number of custom spoilers on the board". The scraper stores it as a post field |
| `thumbnail` BLOB | (thumbs.md) | 38,757 non-null, none on `N` rows |
| `resto` | see above | |

### Live `threads` (9 columns)

| column | corpus | notes |
|---|---|---|
| `op_id` | `thread.no` | |
| `subject` | `thread.subject` | never NULL. HTML-escaped on API threads |
| `semantic_url`, `is_sticky`, `is_closed`, `last_modified_in_api`, `first_seen` | dropped | `first_seen` is when the scraper first saw the thread (up to ~13 h after the OP), not the OP time; `thread.first_time` is the OP post time |
| `is_archived`, `archived_on` | `thread.archived_on` | 168 threads flagged archived, **149 of them with `archived_on = 0`** (b4k-backfilled threads where b4k's `timestamp_expired` was 0). 0 is mapped to NULL |

The corpus `thread` table is derived from `post` (first/last time, counts, prev/next by time) plus
subject and archive time from the sources, so the two threads tables never need to be reconciled.

## 2. Representation differences that matter

| property | parquet legacy | parquet b4k / live `N` | live API |
|---|---|---|---|
| body encoding | HTML | plain text | HTML |
| entities in names, subjects, filenames | escaped | plain | escaped |
| md5 | base64 | base64 | base64 |
| ext | inside `media_filename` | inside `media_filename` | `ext` column, dotted |
| default name | `Anonymous` (25 NULL/empty) | `Anonymous` | `Anonymous` |
| deleted | not recorded | real | real (vanished from API) |
| file spoiler | junk (OP-only count) | real | real |
| file deleted | not recorded | not recorded (b4k `media_status` is not exported) | real |
| capcode normal | NULL | 'N' | NULL |

Plain-text quirks inside b4k rows (kept as stored):

- Post 275941487 holds literal `&amp;` inside several URLs, i.e. it was not unescaped upstream.
  Not touched: unescaping would also alter text users typed.
- Non-ASCII looks degraded in some b4k rows (`??Jelly`, `??jelly##0001` in post 270803207 where
  the original was a symbol): `??` occurs in 517 b4k rows, 3,731 legacy and 614 live; no
  per-source rate difference large enough to prove loss, but it was not investigated.
- b4k plain bodies have no leading/trailing whitespace and no `\r`; the HTML converter strips both
  to match.

## 3. Semantics

- **`timestamp_expired`**: for OPs it is when the thread left 4chan (legacy: 1,798 of 1,896 OPs set,
  98 NULL; b4k: 17 set on OPs that were deleted, 63 are 0 = still live at export time). For replies
  (b4k rows only) it is the **time the post was deleted**: >0 on 21,929 replies, of which 21,865
  have `deleted = 1` (the other 64 have a timestamp but `deleted = 0`). Always NULL on legacy replies.
  The corpus keeps only the OP meaning (`thread.archived_on`); the deletion time is dropped because
  `post` has no column for it.
- **`deleted`**: parquet legacy = unknown (0). The build infers `deleted = 1` for the 4 legacy posts
  newer than the live cutoff that the live scraper never saw (see gate.md). Live deletion means the
  post disappeared from a successful thread fetch, which includes self-deletes, janitor and mod
  deletes, and Cloudflare/API glitches; nothing distinguishes them. 3,077 live + 21,882 parquet
  (23,845 on b4k-source rows, 1,113 on live-source rows, 3 inferred).
- **Ghost posts (subnum > 0)**: none in the parquet (subnum is NULL or 0 everywhere). Decision: drop
  `subnum > 0` rows (they are archive-internal duplicates of deleted posts in foolfuuka) and count
  them in the build report; the count is 0 here.
- **`name` default**: `Anonymous`; empty/NULL names are rewritten to it (25 parquet rows).
- **Cross-source `thread.subject`**: unescaped, so `Virtual Reality General #1708` style subjects are
  comparable across sources. 165 subjects are shared by more than one thread (e.g. the generic
  `/vrg/ - Virtual Reality General` x19, and reposted editions), so subject is not a key.

## 4. HTML forms found and how they convert

Tag counts (legacy + live HTML rows, from `build-report.json`): `<br>` 2.32M, quotelink anchors
1.26M, greentext spans 337k, `<wbr>` 69k, `<s>` 40k, deadlink spans 29k, plain external anchors
105, `<b>` 108, fortune spans 107, emoji spans 51, `<strong>` 2. Dropped as 4chan-injected
decoration (not post text): 23 `like-perk-cnt` badges, 15 `xa23b` and 19 `xa24desu` April Fools
wrappers, 144 `<img>` (emote images). The one **unknown** tag is `<marquee>`, 4 occurrences, all
nested inside a dropped `like-perk-cnt` element (example post 248867583); there are no unknown tags
in kept content. No `<pre class="prettyprint">` exists in this corpus (/vg/ has no code tag), so
`[code]` in the data is always text users typed. See `tests/` for sampled rows of each form.

## 5. Scraper bugs and oddities (chirashi `~/code/vrg-scraper`, read only, not trusted)

1. **`custom_spoiler` stored as a post field and read as if per-post.** 214 OP rows carry 1 (see
   above). Downstream code that treats it as "spoilered image" would blur OP images. The same
   mislabel exists in the parquet's `media_spoiler` (1 on every legacy OP).
2. **`archived_on = 0` for 149 of 168 archived threads** (backfilled from b4k with
   `timestamp_expired = 0`). Any "archived at least 7 days ago" gate based on `archived_on` or on
   `is_archived` alone is wrong for them.
3. **108 threads never flagged archived**, 102 of them with no post for over 7 days: the flag is
   only written while the thread is still fetched, and the monitor stops on 404, so a thread that
   goes from live to 404 between checks keeps `is_archived = 0` forever. Use last post time, not the
   flag, for the settle window.
4. **No un-delete path.** The design says posts reappearing are un-marked, but no code ever sets
   `is_deleted = 0`. `get_archived_post_nos` returns only non-deleted posts, so a reappearing deleted
   post lands in `new_post_nos` and `insert_new_post` would hit the primary-key constraint. No such
   row exists in the data (observed deletions are one-way).
5. **Updates touch only `com` and `filedeleted`.** `name`, `trip`, `sub`, spoiler and file fields are
   never refreshed after first insert; harmless for 4chan but the last `com` wins, so an edited
   post keeps its latest text only.
6. **Backfill rows are second-class.** `vrg_scraper.backfill` ran without `--download-files`: 12,468
   backfilled image rows have a `tim` but no thumbnail BLOB and no local file; they cluster in
   2025-06/07 and 2025-12 to 2026-05 (thumbs.md). `capcode = 'N'` is then the only marker that a
   row is b4k-sourced, and 187 of those rows are HTML (above).
7. **Backfill name handling.** `name or ""` would store empty names for nameless b4k posts (none
   present here: all 48,547 `N` rows have a name).
8. **Deleted detection is "absent from the latest fetch".** A janitor deletion, a self-delete and a
   partial/glitched API response are indistinguishable. A post that was never seen at all (deleted
   within seconds) is simply missing: the 4 posts above exist only in the parquet.
9. `md5`/`fsize` come from the API and the code notes that Cloudflare recompresses images, so they
   will not match the downloaded files on disk (documented in the source). Do not use them to verify
   local files.
10. The scraper was down on days that show as gaps in gate.md (zero or near-zero posts):
    2025-04-15..24, 2025-05-10, 2025-05-16/17, 2026-06-27..30, 2026-09-03..06 (plus a thin
    2026-10-21 and 2022-08-03/04 in the parquet era). Nothing in the DB records scraper downtime.
