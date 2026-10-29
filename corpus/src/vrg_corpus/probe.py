"""Politeness-bound probe of b4k (and archived.moe) thumbnail availability.

At most one request per second, sequential, identifying User-Agent. Stops at the first
429/403 or after 3 consecutive errors. Results are appended to a JSONL file so a stopped
probe can resume without repeating requests.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import duckdb

UA = "vrg-archive (hiina@hiina.space)"
B4K = "https://arch.b4k.dev"
MOE = "https://archived.moe"
MIN_INTERVAL = 1.05
YEARS = range(2018, 2026)
PER_YEAR = 100
MISS_CAP = 10


class StopProbe(Exception):
    """Raised on 429/403 or repeated errors."""


def sample(parquet: Path, per_year: int = PER_YEAR) -> list[dict]:
    """Deterministic sample of non-deleted image posts per year (UTC)."""
    con = duckdb.connect()
    q = f"""
    select * from (
      select post_num, thread_num, timestamp, year(to_timestamp(timestamp)) as y,
             thumb_link, row_number() over (
               partition by year(to_timestamp(timestamp))
               order by hash(post_num::varchar || 'vrg-probe-v1')) as rn
      from read_parquet('{parquet}')
      where media_filename is not null and coalesce(deleted, 0) = 0
        and year(to_timestamp(timestamp)) between 2018 and 2025
    ) where rn <= {per_year} order by y, rn
    """
    cols = ["no", "thread", "ts", "year", "thumb_link", "rn"]
    return [dict(zip(cols, r, strict=True)) for r in con.execute(q).fetchall()]


class Client:
    def __init__(self) -> None:
        self.last = 0.0
        self.consecutive_errors = 0
        self.requests = 0

    def _wait(self) -> None:
        d = MIN_INTERVAL - (time.monotonic() - self.last)
        if d > 0:
            time.sleep(d)
        self.last = time.monotonic()

    def fetch(self, url: str, method: str = "GET") -> tuple[int, bytes, dict]:
        self._wait()
        self.requests += 1
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as f:
                body = f.read() if method == "GET" else b""
                self.consecutive_errors = 0
                return f.status, body, dict(f.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 403):
                raise StopProbe(f"HTTP {e.code} from {url}") from e
            if e.code == 404:
                self.consecutive_errors = 0
                return 404, b"", {}
            self.consecutive_errors += 1
            if self.consecutive_errors >= 3:
                raise StopProbe(f"3 consecutive errors, last HTTP {e.code} {url}") from e
            return e.code, b"", {}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            self.consecutive_errors += 1
            if self.consecutive_errors >= 3:
                raise StopProbe(f"3 consecutive errors, last {e!r} {url}") from e
            return 0, b"", {}


def check_site(client: Client, base: str, no: int) -> dict:
    status, body, _ = client.fetch(f"{base}/_/api/chan/post/?board=vg&num={no}")
    out: dict = {"api_status": status, "found": False, "thumb_link": None, "thumb_status": None}
    if status != 200:
        return out
    try:
        j = json.loads(body)
    except json.JSONDecodeError:
        out["api_status"] = -1
        return out
    if "error" in j:
        out["error"] = j["error"]
        return out
    out["found"] = True
    out["deleted"] = j.get("deleted")
    media = j.get("media")
    if isinstance(media, dict):
        out["media_status"] = media.get("media_status")
        out["thumb_link"] = media.get("thumb_link")
    if out["thumb_link"]:
        s, _, hdrs = client.fetch(out["thumb_link"], method="HEAD")
        out["thumb_status"] = s
        out["thumb_bytes"] = hdrs.get("Content-Length") or hdrs.get("content-length")
    return out


def has_thumb(r: dict) -> bool:
    return r.get("thumb_status") == 200


def run(parquet: Path, log: Path) -> str:
    """Run (or resume) the probe. Returns a stop reason ('' when complete)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, int]] = set()
    rows: list[dict] = []
    if log.exists():
        for line in log.read_text().splitlines():
            r = json.loads(line)
            rows.append(r)
            if r.get("kind") == "stop":
                continue
            done.add((r["site"], r["no"]))
    client = Client()
    smp = sample(parquet)
    reason = ""
    with log.open("a") as fh:

        def emit(r: dict) -> None:
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            rows.append(r)

        try:
            for s in smp:
                if ("b4k", s["no"]) in done:
                    continue
                r = {
                    "site": "b4k",
                    "no": s["no"],
                    "year": s["year"],
                    "ts": s["ts"],
                    "parquet_thumb_link": s["thumb_link"],
                }
                r.update(check_site(client, B4K, s["no"]))
                emit(r)
                done.add(("b4k", s["no"]))
            # archived.moe for up to MISS_CAP misses per year
            per_year_checked: dict[int, int] = defaultdict(int)
            for r in rows:
                if r.get("site") == "moe":
                    per_year_checked[r["year"]] += 1
            by_no = {r["no"]: r for r in rows if r.get("site") == "b4k"}
            for s in smp:
                b = by_no.get(s["no"])
                if b is None or has_thumb(b) or ("moe", s["no"]) in done:
                    continue
                if per_year_checked[s["year"]] >= MISS_CAP:
                    continue
                r = {"site": "moe", "no": s["no"], "year": s["year"], "ts": s["ts"]}
                r.update(check_site(client, MOE, s["no"]))
                emit(r)
                done.add(("moe", s["no"]))
                per_year_checked[s["year"]] += 1
        except StopProbe as e:
            reason = str(e)
            emit({"kind": "stop", "reason": reason, "requests": client.requests})
    return reason


def report(log: Path) -> str:
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    stops = [r for r in rows if r.get("kind") == "stop"]
    b4k = [r for r in rows if r.get("site") == "b4k"]
    moe = [r for r in rows if r.get("site") == "moe"]
    out = ["# b4k thumbnail availability probe", ""]
    out.append(
        f"Sample: up to {PER_YEAR} non-deleted image posts per year (deterministic hash order) "
        f"from the parquet, 2018 to 2025-04. Requests: foolfuuka `post/?board=vg&num=N` on "
        f"`{B4K}`, then HEAD of the returned `thumb_link`. 1 request/s, sequential, "
        f"User-Agent `{UA}`. Total probe records: {len(b4k)} b4k, {len(moe)} archived.moe."
    )
    out.append("")
    if stops:
        out.append("**Probe stopped early:** " + "; ".join(s["reason"] for s in stops))
    else:
        out.append("Probe ran to completion with no 429/403 and no error streak.")
    out += [
        "",
        "## Per year (b4k)",
        "",
        "| year | sampled | API found | thumb_link present | thumb HEAD 200 | available % | "
        "not in b4k | found, no thumb | thumb 404 | other |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    tot = defaultdict(int)
    for y in sorted({r["year"] for r in b4k}):
        rs = [r for r in b4k if r["year"] == y]
        n = len(rs)
        found = sum(r["found"] for r in rs)
        tl = sum(bool(r["thumb_link"]) for r in rs)
        ok = sum(has_thumb(r) for r in rs)
        nf = sum(1 for r in rs if r["api_status"] == 200 and not r["found"])
        nothumb = sum(1 for r in rs if r["found"] and not r["thumb_link"])
        t404 = sum(1 for r in rs if r["thumb_link"] and r.get("thumb_status") == 404)
        other = n - ok - nf - nothumb - t404
        out.append(
            f"| {y} | {n} | {found} | {tl} | {ok} | {100 * ok / n:.0f}% | {nf} | {nothumb} | "
            f"{t404} | {other} |"
        )
        for k, v in (("n", n), ("ok", ok)):
            tot[k] += v
    if tot["n"]:
        out.append(
            f"| all | {tot['n']} | | | {tot['ok']} | {100 * tot['ok'] / tot['n']:.0f}% | | | | |"
        )
    out += ["", "`other` is transport errors or HEAD statuses other than 200/404.", ""]
    pq = [r for r in b4k if r["parquet_thumb_link"]]
    if pq:
        agree = sum(has_thumb(r) for r in pq)
        out.append(
            f"Sampled posts whose parquet row already had a `thumb_link`: {len(pq)}; "
            f"{agree} confirmed live by the API+HEAD."
        )
        out.append("")
    out += ["## Misses checked on archived.moe (at most 10 per year)", ""]
    if moe:
        out += ["| year | checked | found on moe | thumb HEAD 200 |", "|---|---|---|---|"]
        for y in sorted({r["year"] for r in moe}):
            rs = [r for r in moe if r["year"] == y]
            out.append(
                f"| {y} | {len(rs)} | {sum(r['found'] for r in rs)} | "
                f"{sum(has_thumb(r) for r in rs)} |"
            )
    else:
        out.append("None checked.")
    out += ["", "## Example records", ""]
    for r in b4k[:2] + moe[:2]:
        out.append("    " + json.dumps(r))
    return "\n".join(out) + "\n"
