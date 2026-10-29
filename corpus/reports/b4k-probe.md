# b4k thumbnail availability probe

Sample: up to 100 non-deleted image posts per year (deterministic hash order) from the parquet, 2018 to 2025-04. Requests: foolfuuka `post/?board=vg&num=N` on `https://arch.b4k.dev`, then HEAD of the returned `thumb_link`. 1 request/s, sequential, User-Agent `vrg-archive (hiina@hiina.space)`. Total probe records: 800 b4k, 0 archived.moe.

**Probe stopped:** HTTP 403 from https://archived.moe/_/api/chan/post/?board=vg&num=209432315

## Per year (b4k)

| year | sampled | API found | thumb_link present | thumb HEAD 200 | available % | not in b4k | found, no thumb | thumb 404 | other |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | 100 | 0 | 0 | 0 | 0% | 100 | 0 | 0 | 0 |
| 2019 | 100 | 28 | 28 | 28 | 28% | 72 | 0 | 0 | 0 |
| 2020 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| 2021 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| 2022 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| 2023 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| 2024 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| 2025 | 100 | 100 | 100 | 100 | 100% | 0 | 0 | 0 | 0 |
| all | 800 | | | 628 | 78% | | | | |

`other` is transport errors or HEAD statuses other than 200/404.

Sampled posts whose parquet row already had a `thumb_link`: 31; 31 confirmed live by the API+HEAD.

**Coverage boundary.** In the sample, the earliest post b4k has is dated 2019-09-01 and the latest it lacks is dated 2019-08-27: b4k has /vg/ history from about 2019-08 on and nothing before (the earliest b4k-sourced row in the parquet is also 2019-08-26). Every post b4k has in the sample also has a thumbnail that answers HEAD 200 (no 'found, no thumb' or 404 cases), whether or not the parquet row carried a `thumb_link`.

## Misses checked on archived.moe (at most 10 per year)

**Not done.** The first archived.moe request returned HTTP 403, and the brief says to stop at the first 403, so the probe stopped there and did not retry. All 800 b4k records were complete before it. Whether archived.moe has the 2018 to 2019-07 misses is unknown; it needs a browser-like fetch or a manual look.


## Example records

    {"site": "b4k", "no": 209432315, "year": 2018, "ts": 1521876117, "parquet_thumb_link": null, "api_status": 200, "found": false, "thumb_link": null, "thumb_status": null, "error": "Post not found."}
    {"site": "b4k", "no": 217319708, "year": 2018, "ts": 1528419474, "parquet_thumb_link": null, "api_status": 200, "found": false, "thumb_link": null, "thumb_status": null, "error": "Post not found."}
