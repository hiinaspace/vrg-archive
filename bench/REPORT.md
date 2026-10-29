# Search engine study for the archive.vrg.party revamp

Corpus: `vrgarchive-2025-04-11.parquet`, 1,375,527 non-empty posts, 175 MB of plain text (HTML stripped, entities unescaped; `>>N` quote numbers removed from the indexed copy only). Run 2026-10-29 on natto, Chrome 156 (Playwright), a Range-logging server on 127.0.0.1.

## Recommendation and the table

**Recommendation: the worldsearch-style custom sharded index, with doc-id partitions (frozen history plus a growing tail) and newest-first as the default order.** On this corpus it needs about 0.15 to 0.4 MB per cold query plus about 5 KB of startup. It builds in about 70 s (single-threaded Python), is 46 MB of index plus 97 MB of compressed text in about 2,100 files, and a weekly append changes about 3 to 12 MB. Phrases and substrings work by candidate verification against the text blocks (about 0.25 to 0.75 MB). It has no engine to download, and it keeps the Pages file-count and size limits comfortable.

SQLite FTS5 over Range is the credible fallback, and it is near the custom engine on bytes when ordered newest-first (about 0.12 to 0.22 MB). It gets stemming, real phrase search and bm25 for free. Its costs:
- bm25 ordering of a common word reads whole doclists (10 to 14 MB).
- Every query is 25 to 100+ dependent synchronous requests.
- The only usable range VFS (sql.js-httpvfs) was last released in 2021.
- The 317 MB file must be chunked under 25 MiB.

DuckDB-wasm over Parquet range is not competitive for this use: 5.2 MB of engine, then 1.3 to 25 MB per query, because DuckDB's read-ahead pulls whole column chunks. The current site's approach (about 144 MB before the first result) is two orders of magnitude worse than any of these. Pagefind cannot reach this scale (one fragment file per document: about 1.35 million files against Pages' 20,000).

**The evidence limit that matters:** bytes are measured with the real browser clients, but over localhost. Request counts are exact; latency is not (SQLite and DuckDB do synchronous, dependent range requests, the custom engine does about 4 parallel rounds). Search quality was **not** evaluated: the custom engine has no stemming and a hand-rolled bm25-like score, while FTS5 has porter stemming and real bm25. Run the owner's 10 queries through the engine before committing to it.

### Measured numbers

"Cold" means a fresh browser context: nothing cached, engine start included. Bytes are what the server sent (Range responses counted exactly). Static code, which the CDN would compress, is counted as brotli of the whole file and shown as "startup". Rare is the mean of 5 words (yamada, curation, creepypasta, czechvr, seasick), common is the mean of vrchat, game, anyone, headset and quest, phrase is the mean of "mic spam", "public avatars" and "index controllers", substr is `wrld_`, and date is `vrchat` in 2023. All queries return the first 20 results with text. Sizes use 1 KB = 1024 bytes and M = MiB.

| Engine / config | Build | Index bytes (text bytes) | Files | Startup | Rare | Common | Phrase | Substr | Date | Requests rare/common/phrase/substr/date | Weekly +4k posts changes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Current site** (DuckDB-wasm, whole FTS tables in memory) | prebuilt | 44.5 MB index + 91.6 MB posts parquet | n/a | **144 MB total before the first result, 108 requests, 19.5 s to first result** (wasm 6.5 MB br included) | same | same | n/a (OR semantics, no phrase) | n/a | n/a | n/a | everything (rebuilt tar) |
| **SQLite FTS5** (porter, detail=full, contentless) + sql.js-httpvfs, newest-first | 16 s | 105 MB (+212 MB posts, uncompressed) = 317.6 MB | 19 chunks of 16 MiB | 411 KB | 124 KB | 117 KB | 191 KB | 132 KB | 120 KB | 29/27/43/30/28 | 1.0 MB of pages, but 3 of 19 chunks (48 MB) |
| SQLite FTS5, **bm25 order** | same | same | same | 411 KB | 460 KB | **13.2 MB** | **7.0 MB** | 132 KB | 2.4 MB | 73/74/108/30/60 | same |
| **Custom E** (2 partitions x 1024 buckets), newest-first | 72 s | 46.1 MB (+97 MB text) = 143 MB | 2,097 | 2.4 KB | 142 KB | 172 KB | 424 KB | 205 KB | 151 KB | 12/21/64/32/16 | **12.4 MB** (tail partition + last 2 MB text pack) |
| Custom E, relevance order | same | same | same | 2.4 KB | 142 KB | 323 KB | 438 KB | 253 KB | 257 KB | 12/43/43/44/40 | same |
| Custom D (6 partitions x 128), newest-first (same shards as A, 2 MB text packs) | 71 s | 47.1 MB (+97 MB) | 817 | 2.4 KB | 482 KB | 175 KB | 707 KB | 232 KB | 198 KB | 16/21/62/32/16 | **3.2 MB** (2.5 MB tail shards + 0.7 MB pack) |
| Custom B (1 partition x 1024) | 69 s | 45.4 MB (+97 MB) | 1,032 | 2.4 KB | 148 KB | 231 KB | 565 KB | 223 KB | 241 KB | 11/21/63/32/16 | 58.6 MB (all shards) |
| **DuckDB-wasm + Parquet over range** (term,doc,tf postings + docs parquet; row groups 30k / 4096), newest-first | 7 s | 85 MB postings + 80 MB docs | 2 | 5.2 MB (+0.67 MB parquet extension, uncounted) | 6.8 MB | 1.3 MB | 13.6 MB | 2.5 MB | 1.6 MB | 52/26/80/24/25 | rewrites both files (about 165 MB) unless split |
| DuckDB-wasm + Parquet, row groups 8k / 1024 | 4 s | 84 + 83 MB | 2 | 5.2 MB | 4.3 MB | 2.0 MB | 10.6 MB | 3.3 MB | 1.9 MB | 61/49/111/27/44 | same |
| Pagefind 1.5.2 (extrapolated from 50k and 200k samples) | 27 s at 50k, 283 s at 200k (about 2 h extrapolated at 1.4M) | 51 MB at 200k | **196,289 files at 200k** (about 1.35M at full size) | not run | | | | | | | not feasible on Pages (20,000 file limit) |
| SQLite FTS5 trigram (true substring) | 62 s | 507 MB index (4.9x the word index) | | not run | | | | | | | rejected on size |

Notes on the table:
- Custom "newest-first" stops at the first 20 verified hits, starting from the newest partition. "Relevance" fetches every partition's postings, scores bm25-style with a 6-bit tf and length bucket packed per posting, then fetches the text for the top 20. Phrase and substring results are verified against the text, so their byte cost depends on the false-candidate rate (see "public avatars": 811 candidates for 188 true matches).
- Startup for the custom engine is the 6 KB page script plus a 2 KB manifest. A real UI would add a bundle, but not an engine.
- The custom partition layout is a real tradeoff. More partitions mean cheaper weekly changes (D: 3.2 MB) but more fixed requests per rare term (16 against 11). One partition gives the cheapest queries and rewrites everything weekly (B: 58.6 MB). Two partitions (E) is a reasonable middle. The tail partition grows until it rolls over, so E's weekly change grows from about 12 MB to about 40 MB. A smaller tail (D-style, 262k docs) caps it at about 11 MB.
- SQLite's weekly cost is the append-without-`optimize` case (253 pages touched). A later `optimize` would dirty most of the file.

## 1. The current site

Source is the Observable Framework project on master (`src/*.md`, `src/data/*.sh`).

**How it searches.**
- `src/data/vrgindex.tar.sh` only curls a prebuilt `vrgarchive-2025-04-11-fts-index.tar` (136,120,320 B) from file.vrg.party, and `vrgarchive.parquet.sh` curls the 91,626,366 B posts parquet. Both are build-time inputs. The built site ships the unpacked `fts_main_posts_{dict,docs,fields,stats,stopwords,terms}.parquet` plus the posts parquet.
- The full-text page (`full-text-search.md`) starts a DuckDB-wasm 1.29.0 instance and `LOAD fts` (the extension is downloaded from extensions.duckdb.org). It then runs `CREATE TABLE ... AS FROM '<url>'` for every index table and for the posts table, which pulls the whole of each file into wasm memory. It re-creates the `tokenize` and `match_bm25` macros from DuckDB's FTS extension by hand.
- Each query is `select ... from (select *, fts_main_posts.match_bm25(post_num, term) as score from posts) where score is not null order by score desc`. That is DuckDB's FTS: porter-stemmed terms, 571 English stopwords, bm25, and **disjunctive (OR) matching** (conjunctive is off). There is no phrase support, no operators and no date filter.
- The query input is a bare `Inputs.text` with no debounce, so it re-runs on every keystroke, and the default query `sneed` runs on load. All matches are returned and rendered in one `Inputs.table`. Each comment is injected via `innerHTML` after DOMPurify.
- The substring page runs `contains(lower(comment), term)` over all 1.4M rows, debounced, and plots counts per month. The thread browser does `group by thread_num` over the whole table, then `select * where thread_num = ...`.

**What a cold visitor downloads.** Measured with Playwright against the live site (fast connection, nothing cached):
- 144,134,640 bytes in 108 requests before "292 results." appears for the default query.
- The wasm engine is 6.56 MB brotli.
- The posts parquet comes in 16 MB range pieces totalling 91.6 MB; the index parquets total about 44.5 MB (terms 40.4 MB, docs 3.1 MB, dict 0.95 MB).
- First result: 19.5 s. The DuckDB FTS extension download is on top of that.
- Every later page (thread browser, substring search) downloads the 91.6 MB posts parquet again. The browser may cache it.

**Janky.**
- The 144 MB up-front download is the architecture: tables are materialized in memory, not range-read.
- The index tokenizer is applied to **raw HTML** (the `comment` column still contains `<a class="quotelink">` markup and entities). The dictionary shows `gt` in 1,082,255 docs, `href` in 1,016,516 and `quotelink` in 1,016,479, so the markup tokens pollute ranking and phrase intent. The tokenizer also deletes digits, so `4090` is unsearchable, and `wrld_` becomes `wrld`.
- Multi-word queries are OR with bm25, so "quest pro" matches every post with either word.
- There is no pagination, no date filter, no link from a hit to its thread (the thread browser is a separate page with no thumbnails), and the page says it breaks under Firefox "advanced tracking protection".
- Mutations need the whole index rebuilt, and a 136 MB tar is the unit of update.

## 2. Survey

Index size and bytes per query are for about 1.4M short posts: measured for the rows marked (measured), otherwise from documentation.

| Approach | Index size | Bytes per query | Phrase | Ranking | CJK / substring | Incremental | Maturity |
|---|---|---|---|---|---|---|---|
| DuckDB-wasm FTS as on the current site ([FTS extension docs](https://duckdb.org/docs/2.0/core_extensions/full_text_search.html), [wasm](https://github.com/duckdb/duckdb-wasm)) | 44.5 MB + 91.6 MB (measured) | whole index first: 144 MB | not documented | bm25, porter, 571 stopwords | none / separate scan | rebuild, or `incremental=1` with triggers (native only) | maintained; wasm 1.32.0 stable, 1.33.1-dev on npm `latest` |
| DuckDB-wasm reading Parquet over HTTP Range | 165 MB (measured, hand-built postings) | 1.3 to 25 MB plus 5.2 MB engine (measured) | by verifying text | whatever you write in SQL | `contains` on candidates | rewrite files | works, but needs the server to answer `HEAD` with `Range` with a 206 and the config `forceFullHTTPReads:false`, `allowFullHTTPReads:false`. Under defaults it silently downloads the whole file (found while measuring). |
| SQLite FTS5 in the browser over Range: [sql.js-httpvfs](https://github.com/phiresky/sql.js-httpvfs) 0.8.12 (2021, unmaintained), [sqlite-wasm-http](https://github.com/mmomtchev/sqlite-wasm-http) (official sqlite-wasm + HTTP VFS, "experimental", no release listed) | 105 MB + posts (measured); trigram 507 MB | newest-first 0.12 to 0.22 MB; bm25 7 to 14 MB common (measured) | native, positional | bm25 (needs whole doclist), porter | trigram tokenizer only (5x size) | append works (253 pages touched); `optimize` rewrites | FTS5 is rock solid; the range VFS layer is the fragile part. sqlite-wasm-http advises 1 KB pages. No official range VFS exists (official OPFS only). |
| [Pagefind](https://pagefind.app/) 1.5.2 (April 2026) | 51 MB at 200k (measured); 13.7 MB at 50k | tens of KB for 10k pages (their claim) | yes (quoted) | own scoring, word-position | CJK segmented | full rebuild | very mature, but designed for tens of thousands of pages. One fragment file per page: 196,289 files and 283 s at 200k docs (measured). Hugo-forum reports crashes at 300k to 500k pages ([thread](https://discourse.gohugo.io/t/scaling-pagefind-to-over-1-million-pages/56109)). |
| tantivy (Rust) | roughly Lucene-sized | needs a range `Directory` | yes | bm25 | tokenizers incl. ngram | segments | Static-over-HTTP exists only natively ([tantivy-uffd](https://docs.rs/tantivy-uffd), Linux only). No maintained tantivy-wasm found; I did not build one. |
| [hermes-wasm](https://cdn.jsdelivr.net/npm/hermes-wasm@1.8.109/README.md) (Hermes search engine in wasm) | not stated | `RemoteIndex` over HTTP range with slice caching (per its README) | yes | BM25 | not stated | not stated | 3 MB wasm (1.2 MB gz). Interesting, unverified, no scale claims. |
| [InfiSearch / morsels](https://github.com/ang-zeyu/morsels) 0.10.1 | | | boolean + phrase | BM25 + proximity | | incremental | deprecated by its author; recommends Pagefind |
| [docfind](https://code.visualstudio.com/blogs/2026/01/15/docfind) (Microsoft, Jan 2026) | 2.7 MB br at 50k docs | whole index loads | no | keyword (RAKE) | fuzzy | rebuild | demo-scale (50k docs); whole index in memory |
| tinysearch / Lunr / MiniSearch / FlexSearch / Orama | grow linearly | whole index in memory | varies | varies | varies | rebuild | designed for thousands of docs, not 1.4M |
| **Custom sharded inverted index** (worldsearch-style, [vrcwscrape `search/`](https://github.com/hiinaspace/vrcwscrape/tree/search-static/search)) | 46 MB (+97 MB text) (measured) | 0.14 to 0.7 MB (measured) | candidate verification, no positions | bm25-like, newest-first | tokens only; mid-word substring needs a vocabulary scan or trigrams | tail partition only (3 to 12 MB) | the owner already runs this design on 218k worlds |

Cloudflare Pages limits (checked against [the docs](https://developers.cloudflare.com/pages/platform/limits/) 2026-10-29): 20,000 files on the free plan (100,000 on paid with wrangler 4), 25 MiB per file.

## 3. Method

All code is in this directory. `prep.py` builds the corpus; the `build_*.py` files build each index; `server.mjs` is the Range logger; `run_*.mjs` drive Chrome; `incr*.py` measure weekly deltas; `results/` has the raw JSONL and build logs.

- **Corpus.** `prep.py` strips tags, unescapes entities and keeps non-empty comments, ordered by timestamp, with `id` = position. Rare words were drawn by `hash(w)` from words with 5 to 20 postings. Common words are the owner's list. The date filter is `vrchat` for 2023-01-01 to 2023-12-31 (id range 1,108,972 to 1,238,837, which the client gets from a small manifest; a naive `WHERE ts` scan cost 215 MB on SQLite, so this lookup must be in the manifest).
- **Measurement.** Every query runs in a fresh browser context (nothing cached) against `server.mjs`, which logs each request's URL, `Range` header and actual bytes streamed. Two bugs were found and fixed in the harness. First, HEAD requests were counted as bodies (sql.js-httpvfs sends HEAD, giving a false 317 MB). Second, DuckDB-wasm needs a 206 answer to `HEAD` with `Range: bytes=0-`; otherwise it silently falls back to a full download. "Startup" sums brotli-compressed static files fetched (page script, worker, wasm) once per fresh context. Data bytes are raw bytes served, because Cloudflare does not recompress Range responses and the custom shards are already gzip.
- **SQLite.** FTS5, `porter unicode61 remove_diacritics 2`, `detail=full`, contentless, page size 4096, `optimize` and `vacuum`. One DB holds `post(id,ts,no,text)` and the index. It is served as 16 MiB chunks through sql.js-httpvfs 0.8.12 in chunked mode (so it also satisfies the 25 MiB file limit), `requestChunkSize` 4096, in a real worker. Queries `MATCH` + `rowid BETWEEN` for dates and `ORDER BY rowid DESC` (newest) or `ORDER BY rank` (bm25), `LIMIT 20`; phrases as `"a b"`; substring as `MATCH 'wrld'` plus `LIKE '%wrld\_%'` on the post text. This is a real-browser measurement, not a simulated VFS.
- **Custom.** `build_custom.py` and `web/custom.js`. Tokens are NFKC-lowercased `[\p{L}\p{N}]+`, with no stemming. Doc ids are in time order and are split into partitions of PS docs. A term lives in the shard `idx/p<partition>/<fnv(term) mod B>.bin` (gzip, a term directory with df and offsets, then varint postings of `delta<<6 | tf2 | lenbucket4`). Stopwords (df > 20%, 8 words) are skipped for retrieval. Text is stored in gzip blocks of 64 posts in pack files fetched with Range (a 40 KB offsets table is loaded lazily). Phrase and substring queries intersect the posting lists, then verify candidates in batches of 40 until 20 hits are found. The pack size matters for weekly churn (16 MiB packs rewrite 13 MB of text weekly; 2 MiB packs rewrite 0.7 MB).
- **DuckDB-wasm.** v1.32.0 (the npm `latest`, 1.33.1-dev57, behaves the same), eh bundle, queries over `postings.parquet` (term, doc, tf; sorted by term, doc; zstd) and `docs.parquet` (id, ts, no, text; sorted by id). Step 1 gets the newest candidate doc ids with a `GROUP BY doc HAVING count(*) = n`; step 2 fetches the rows with `id IN (...)`.
- **Old site.** Playwright against https://archive.vrg.party/full-text-search (`old_site.mjs`), summing `request.sizes()` until "N results." appeared.
- **Incremental.** `incr.py` rebuilds with the last 4,000 posts removed and compares file hashes (the custom engine; whole-file granularity, as a Pages deploy would see it). `incr_sqlite.py` builds a DB without the last 4,000 posts, appends them without `optimize`, and compares 4 KiB pages and 16 MiB chunks.
- **Pagefind.** `pf/build_pf.mjs` (Node API `addCustomRecord`, 50k and 200k random posts).

### Not measured

- Real network latency and Cloudflare behavior. Local timings (30 to 600 ms per query) are not representative. Dependent round trips are: custom about 4 parallel rounds (manifest, shards, offsets, text blocks, plus one more per 40-candidate verification batch); sql.js-httpvfs and DuckDB-wasm issue sequential synchronous requests (25 to 110 per query), which at 50 ms RTT would be 1.5 to 5 s. This is an estimate.
- Search quality and recall against the owner's queries. The custom engine's counts match whole-token counts (for example `vrchat`: 50,681 against 50,623 by regex, 50,747 by DuckDB's stemmer), but stemming (`headsets`, `avatars`) is absent.
- Pages' `*.pages.dev` Range behavior (worldsearch found it answers 200 there; the custom domain gives 206). The custom engine's text packs and the SQLite chunks need Range on the custom domain.
- DuckDB's own FTS index attached over Range (the hand-built postings table was used instead), memory use on phones, and a tantivy-wasm build.
