"""Brute-force check of engine counts against the corpus SQLite (independent filter + SQL; shared tokenizer).

usage: uv run python oracle/check_counts.py [--data DIST/data] [--db corpus.sqlite]
Runs web/test/dump.ts over a query list, then recomputes every number by scanning posts in Python.
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from vrg_site import text, tok

SITE = Path(__file__).resolve().parents[1]
DATA = Path("/home/s/code/vrg-archive-data")
SNAP = 1793306940


# query string -> predicate over a post dict (tokens `t`, greentext tokens `g`, row fields)
def has(w):
    s = tok.stem(w)
    return lambda p: s in p["t"]


def phrase(*ws):
    seq = [tok.stem(w) for w in ws]
    n = len(seq)
    return lambda p: any(p["tl"][i : i + n] == seq for i in range(len(p["tl"]) - n + 1))


CASES = {
    "vrchat": has("vrchat"),
    "slop": has("slop"),
    "headset latency": lambda p: has("headset")(p) and has("latency")(p),
    '"headset latency"': phrase("headset", "latency"),
    '"valve deckard"': phrase("valve", "deckard"),
    "deckard": has("deckard"),
    "sneedup": has("sneedup"),
    "outer wilds": lambda p: has("outer")(p) and has("wilds")(p),
    "quest -pro": lambda p: has("quest")(p) and not has("pro")(p),
    '"na tea"': phrase("na", "tea"),
    "ai | llm | gpt": lambda p: has("ai")(p) or has("llm")(p) or has("gpt")(p),
    "vrchat has:image": lambda p: has("vrchat")(p) and p["ext"],
    "vrchat ext:png": lambda p: has("vrchat")(p) and p["ext"] == ".png",
    "vrchat op:yes": lambda p: has("vrchat")(p) and p["op"],
    "vrchat -has:image": lambda p: has("vrchat")(p) and not p["ext"],
    "vrchat date:2020": lambda p: has("vrchat")(p) and p["year"] == 2020,
    "vrchat date:2020-03..2020-05": lambda p: (
        has("vrchat")(p) and "2020-03" <= p["ym"] <= "2020-05"
    ),
    "greentext:implying": lambda p: tok.stem("implying") in p["g"],
    "thread:1500 quest": lambda p: p["ed"] == 1500 and has("quest")(p),
    "domain:youtube.com": lambda p: "youtube.com" in p["doms"],
    "replies:>=5": lambda p: p["rep"] >= 5,
    "replies:>=3 vrchat": lambda p: p["rep"] >= 3 and has("vrchat")(p),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA / "site-r1/dist/data"))
    ap.add_argument("--db", default=str(DATA / "corpus-20261029/vrgarchive.sqlite"))
    ap.add_argument("--out", default=str(DATA / "site-r1/check_counts.json"))
    a = ap.parse_args()
    tmp = Path(a.out).with_suffix(".queries.json")
    tmp.write_text(json.dumps(list(CASES)))
    dump = Path(a.out).with_suffix(".engine.json")
    subprocess.run(
        ["node", "build.mjs", "--run", "test/dump.ts", a.data, str(tmp), str(dump)],
        cwd=SITE / "web",
        check=True,
    )
    eng = json.loads(dump.read_text())

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    cutoff = SNAP - 7 * 86400
    ed = {}
    ok_threads = set()
    for no, subj, last in con.execute("select no, subject, last_time from thread"):
        if last < cutoff:
            ok_threads.add(no)
            m = re.search(r"#(\d+)", subj or "")
            ed[no] = int(m[1]) if m else 0
    live = {
        r[0]
        for r in con.execute("select no, thread_no from post where deleted=0")
        if r[1] in ok_threads
    }
    rep = Counter()
    for f, t in con.execute("select from_no, to_no from quote"):
        if f in live and t in live:
            rep[t] += 1
    got = {q: {"total": 0, "months": Counter()} for q in CASES}
    extra = {q: Counter() for q in CASES}
    n = 0
    for no, th, ts, body, ext in con.execute(
        "select no, thread_no, time, body, file_ext from post where deleted=0"
    ):
        if th not in ok_threads:
            continue
        n += 1
        tl = tok.tokens(body)
        d = datetime.fromtimestamp(ts, UTC)
        p = {
            "t": set(tl),
            "tl": tl,
            "g": set(tok.tokens(tok.greentext(body))),
            "ext": ext or "",
            "op": no == th,
            "year": d.year,
            "ym": d.strftime("%Y-%m"),
            "ed": ed[th],
            "rep": rep.get(no, 0),
            "doms": text.domains(body),
        }
        for q, fn in CASES.items():
            if fn(p):
                got[q]["total"] += 1
                got[q]["months"][p["ym"]] += 1
                extra[q]["image"] += bool(ext)
                extra[q]["op"] += no == th
    bad = 0
    for q in CASES:
        e = eng[q]
        months_ok = dict(got[q]["months"]) == e["months"]
        ok = (
            e["total"] == got[q]["total"]
            and months_ok
            and e["image"] == extra[q]["image"]
            and e["op"] == extra[q]["op"]
        )
        bad += not ok
        print(
            f"{'OK ' if ok else 'BAD'} {q!r}: engine {e['total']} brute {got[q]['total']} months_equal={months_ok} image {e['image']}/{extra[q]['image']} op {e['op']}/{extra[q]['op']}"
        )
    print(f"{n} posts scanned; {bad} mismatches")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
