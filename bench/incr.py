import hashlib, os, sys
def h(d):
    r = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(root, f); r[os.path.relpath(p, d)] = (hashlib.md5(open(p,'rb').read()).hexdigest(), os.path.getsize(p))
    return r
for a in sys.argv[1:]:
    new, old = h(f"out/{a}"), h(f"out/{a}_old")
    ch = {k: v for k, v in new.items() if old.get(k, (None,))[0] != v[0]}
    print(a, "files changed", len(ch), "of", len(new), "bytes", sum(v[1] for v in ch.values()), "of", sum(v[1] for v in new.values()))
    print("   idx:", sum(v[1] for k, v in ch.items() if k.startswith("idx")), "docs:", sum(v[1] for k, v in ch.items() if k.startswith("docs")))
