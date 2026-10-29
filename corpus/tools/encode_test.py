"""Measure JPEG vs WebP vs AVIF for fetched thumbnails at matched visual quality.

usage: encode_test.py <store> <outdir> [N=500]
Per file the quality is searched until mean SSIM (7x7 box, luma) against the decoded original
reaches TARGET; sizes are totals over the sample. Writes up to 6 side-by-side stills.
"""

from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TARGET = 0.985


def box(a: np.ndarray, k: int = 7) -> np.ndarray:
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def ssim(a: Image.Image, b: Image.Image) -> float:
    x = np.asarray(a.convert("L"), dtype=np.float64)
    y = np.asarray(b.convert("L"), dtype=np.float64)
    if min(x.shape) < 8:
        return 1.0 if np.array_equal(x, y) else float(1 - np.abs(x - y).mean() / 255)
    mx, my = box(x), box(y)
    vx, vy, cxy = box(x * x) - mx**2, box(y * y) - my**2, box(x * y) - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx**2 + my**2 + c1) * (vx + vy + c2))
    return float(s.mean())


def enc(im: Image.Image, fmt: str, q: int) -> bytes:
    b = io.BytesIO()
    if fmt == "AVIF":
        im.save(b, "AVIF", quality=q, speed=6)
    else:
        im.save(b, "WEBP", quality=q, method=4)
    return b.getvalue()


def matched(im: Image.Image, fmt: str) -> tuple[bytes, int, float]:
    lo, hi = 20, 95
    best = enc(im, fmt, hi)
    bq = hi
    while lo < hi:
        mid = (lo + hi) // 2
        d = enc(im, fmt, mid)
        if ssim(im, Image.open(io.BytesIO(d)).convert("RGB")) >= TARGET:
            best, bq, hi = d, mid, mid
        else:
            lo = mid + 1
    return best, bq, ssim(im, Image.open(io.BytesIO(best)).convert("RGB"))


def main() -> None:
    store, out = Path(sys.argv[1]), Path(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    out.mkdir(parents=True, exist_ok=True)
    files = sorted((store / "raw").glob("*/*.jpg"))
    random.Random(1).shuffle(files)
    files = files[:n]
    tot = {"jpeg": 0, "webp": 0, "avif": 0, "webp75": 0, "avif50": 0}
    qs: dict[str, list[int]] = {"webp": [], "avif": []}
    ss: dict[str, list[float]] = {"webp": [], "avif": []}
    rows = []
    for f in files:
        raw = f.read_bytes()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        tot["jpeg"] += len(raw)
        r = {"f": f.name, "jpeg": len(raw), "im": im}
        for fmt in ("WEBP", "AVIF"):
            d, q, s = matched(im, fmt)
            k = fmt.lower()
            tot[k] += len(d)
            qs[k].append(q)
            ss[k].append(s)
            r[k] = d
        tot["webp75"] += len(enc(im, "WEBP", 75))
        tot["avif50"] += len(enc(im, "AVIF", 50))
        rows.append(r)
    print(f"n={len(rows)} target mean-SSIM>={TARGET}")
    for k, v in tot.items():
        print(
            f"{k:7s} total {v / 1024:9.1f} KiB  mean {v / len(rows):7.0f} B  {v / tot['jpeg']:.2f}x"
        )
    for k in qs:
        print(k, "median q", int(np.median(qs[k])), "mean ssim", round(float(np.mean(ss[k])), 4))
    # stills: 6 sample rows, each tile = original | webp | avif, upscaled 3x to judge
    rows.sort(key=lambda r: -r["jpeg"])
    pick = [rows[i] for i in np.linspace(0, len(rows) - 1, 6).astype(int)]
    for j, r in enumerate(pick):
        ims = [
            r["im"],
            Image.open(io.BytesIO(r["webp"])).convert("RGB"),
            Image.open(io.BytesIO(r["avif"])).convert("RGB"),
        ]
        w, h = ims[0].size
        sheet = Image.new("RGB", (w * 9 + 20, h * 3), "white")
        for k, t in enumerate(ims):
            sheet.paste(t.resize((w * 3, h * 3), Image.NEAREST), (k * (w * 3 + 10), 0))
        sheet.thumbnail((1600, 1600))
        sheet.save(out / f"compare-{j + 1}-jpeg-webp-avif.jpg", quality=92)
    for j, r in enumerate(pick):
        print(f"still {j}: jpeg {r['jpeg']} webp {len(r['webp'])} avif {len(r['avif'])}")


if __name__ == "__main__":
    main()
