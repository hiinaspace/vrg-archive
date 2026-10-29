"""Custom sharded inverted index (worldsearch-style), partitioned by doc-id range.
usage: build_custom.py OUT PS BUCKETS [LIMIT]"""
import sys, os, re, json, gzip, math, time, unicodedata, struct, hashlib
import pyarrow.parquet as pq
out, PS, B = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else None
BS = 64; PACK = int(os.environ.get("PACK_MB", "16")) * 1024 * 1024
TOK = re.compile(r"[^\W_]+")
t0 = time.time()
tbl = pq.read_table("data/corpus.parquet", columns=["id", "no", "ts", "text", "idx"]).to_pydict()
N = len(tbl["id"]) if LIMIT is None else LIMIT
ids, nos, tss, texts, idxs = (tbl[k][:N] for k in ("id", "no", "ts", "text", "idx"))
def fnv(s):
    h = 0x811c9dc5
    for b in s.encode(): h = ((h ^ b) * 0x01000193) & 0xffffffff
    return h
def varint(n, o):
    while n >= 0x80: o.append((n & 0x7f) | 0x80); n >>= 7
    o.append(n)
def tokens(s): return TOK.findall(unicodedata.normalize("NFKC", s).lower())
os.makedirs(out + "/idx", exist_ok=True); os.makedirs(out + "/docs", exist_ok=True)
def w(path, data): 
    with open(path, "wb") as f: f.write(gzip.compress(data, 9, mtime=0))
    return os.path.getsize(path)
# stopwords: df over whole corpus > 20% of docs
dfall = {}
parts = (N + PS - 1) // PS
totlen = 0
stats = {"shard_bytes": 0, "nshards": 0, "postings": 0}
partdf = []
for p in range(parts):
    lo, hi = p * PS, min(N, (p + 1) * PS)
    buckets = [dict() for _ in range(B)]
    for i in range(lo, hi):
        tk = tokens(idxs[i]); L = len(tk); totlen += L
        lb = min(15, int(math.log2(L + 1) * 1.6))
        c = {}
        for t in tk: c[t] = c.get(t, 0) + 1
        for t, tf in c.items():
            b = buckets[fnv(t) % B]
            b.setdefault(t, []).append((i, ((min(tf, 3) - 1) << 4) | lb))
    pdf = {}
    for b, d in enumerate(buckets):
        if not d: continue
        entries = []; body = bytearray()
        for t in sorted(d):
            pl = d[t]; prev = lo - 1; o = bytearray()
            for (i, low) in pl:
                varint(((i - prev - 1) << 6) | low, o); prev = i
            entries.append((t.encode(), len(pl), len(o))); body += o
            pdf[t] = len(pl); stats["postings"] += len(pl)
        hdr = bytearray(); varint(len(entries), hdr)
        for tb, df, ln in entries:
            varint(len(tb), hdr); hdr += tb; varint(df, hdr); varint(ln, hdr)
        os.makedirs(f"{out}/idx/p{p}", exist_ok=True)
        stats["shard_bytes"] += w(f"{out}/idx/p{p}/{b}.bin", bytes(len(hdr).to_bytes(4, "little")) + bytes(hdr) + bytes(body)); stats["nshards"] += 1
    for t, n in pdf.items(): dfall[t] = dfall.get(t, 0) + n
    print("part", p, lo, hi, time.time() - t0, flush=True)
stop = sorted(t for t, n in dfall.items() if n > 0.20 * N)
# doc blocks
packs = []; cur = bytearray(); offs = []; packfirst = []; blk = 0
def flushpack():
    global cur
    if cur:
        k = len(packs); sz = w(f"{out}/docs/pack{k}.bin", b"") if False else None
        with open(f"{out}/docs/pack{k}.bin", "wb") as f: f.write(cur)
        packs.append({"file": f"docs/pack{k}.bin", "first": packfirst[-1], "size": len(cur)}); cur = bytearray()
for s in range(0, N, BS):
    data = json.dumps([[nos[i], tss[i], texts[i]] for i in range(s, min(N, s + BS))], ensure_ascii=False, separators=(",", ":")).encode()
    z = gzip.compress(data, 9, mtime=0)
    if not cur: packfirst.append(blk)
    if len(cur) + len(z) > PACK: flushpack(); packfirst.append(blk)
    offs.append(len(cur)); cur += z; blk += 1
flushpack()
ob = bytearray(); prev = 0
for o in offs: varint(o if o >= prev else o, ob); prev = o   # per-pack offsets, absolute (not delta): reset at pack boundaries
off_size = w(f"{out}/docs/offsets.bin", bytes(ob))
months = {}
import datetime
mfirst = []
last = None
for i in range(N):
    d = datetime.datetime.fromtimestamp(tss[i], datetime.UTC); k = d.year * 12 + d.month - 1
    if k != last: mfirst.append([k, i]); last = k
man = {"N": N, "PS": PS, "B": B, "BS": BS, "parts": parts, "packs": packs, "stop": stop, "avgdl": totlen / N, "months": mfirst, "offsets": "docs/offsets.bin"}
json.dump(man, open(out + "/manifest.json", "w"), separators=(",", ":"))
tot = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs)
idxbytes = stats["shard_bytes"]
print(json.dumps({"N": N, "PS": PS, "B": B, "build_s": time.time() - t0, "index_bytes": idxbytes, "nshards": stats["nshards"], "postings": stats["postings"], "docs_bytes": sum(p["size"] for p in packs), "total_bytes": tot, "stop": stop[:40], "nstop": len(stop)}))
