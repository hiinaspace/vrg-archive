// Fixed-size bitsets over doc ids (Uint32Array words).
export type Bits = Uint32Array;
export const words = (n: number) => (n + 31) >>> 5;
export const mkBits = (n: number): Bits => new Uint32Array(words(n));
export const setBit = (b: Bits, i: number) => { b[i >>> 5] |= 1 << (i & 31); };
export const hasBit = (b: Bits, i: number) => (b[i >>> 5] >>> (i & 31)) & 1;

export function popcnt32(x: number): number {
  x = x - ((x >>> 1) & 0x55555555);
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}
export function count(b: Bits): number { let c = 0; for (let i = 0; i < b.length; i++) if (b[i]) c += popcnt32(b[i]); return c; }

/** number of set bits with index in [lo, hi) */
export function countRange(b: Bits, lo: number, hi: number): number {
  if (hi <= lo) return 0;
  const wl = lo >>> 5, wh = (hi - 1) >>> 5;
  const ml = ~0 << (lo & 31) >>> 0;
  const mh = (hi & 31) === 0 ? 0xffffffff : ((1 << (hi & 31)) - 1) >>> 0;
  if (wl === wh) return popcnt32((b[wl] & ml & mh) >>> 0);
  let c = popcnt32((b[wl] & ml) >>> 0);
  for (let w = wl + 1; w < wh; w++) if (b[w]) c += popcnt32(b[w]);
  return c + popcnt32((b[wh] & mh) >>> 0);
}
export function and(a: Bits, b: Bits): Bits { const o = new Uint32Array(a.length); for (let i = 0; i < o.length; i++) o[i] = a[i] & b[i]; return o; }
export function or(a: Bits, b: Bits): Bits { const o = new Uint32Array(a.length); for (let i = 0; i < o.length; i++) o[i] = a[i] | b[i]; return o; }
export function andNot(a: Bits, b: Bits): Bits { const o = new Uint32Array(a.length); for (let i = 0; i < o.length; i++) o[i] = a[i] & ~b[i]; return o; }
export function not(a: Bits, n: number): Bits {
  const o = new Uint32Array(a.length);
  for (let i = 0; i < o.length; i++) o[i] = ~a[i];
  if (n & 31) o[o.length - 1] &= (1 << (n & 31)) - 1;
  return o;
}
export function full(n: number): Bits { return not(new Uint32Array(words(n)), n); }
export function range(n: number, lo: number, hi: number): Bits {
  const o = new Uint32Array(words(n));
  lo = Math.max(0, lo); hi = Math.min(n, hi);
  if (hi <= lo) return o;
  const wl = lo >>> 5, wh = (hi - 1) >>> 5;
  for (let w = wl; w <= wh; w++) {
    let m = 0xffffffff;
    if (w === wl) m &= ~0 << (lo & 31);
    if (w === wh && (hi & 31)) m &= (1 << (hi & 31)) - 1;
    o[w] = m >>> 0;
  }
  return o;
}
/** call fn(i) for each set bit, ascending */
export function forEach(b: Bits, fn: (i: number) => void): void {
  for (let w = 0; w < b.length; w++) {
    let x = b[w];
    while (x) { const t = x & -x; fn((w << 5) + (31 - Math.clz32(t))); x ^= t; }
  }
}
/** set bits in descending order */
export function forEachDesc(b: Bits, fn: (i: number) => boolean | void): void {
  for (let w = b.length - 1; w >= 0; w--) {
    let x = b[w];
    while (x) { const hb = 31 - Math.clz32(x); if (fn((w << 5) + hb) === false) return; x ^= 1 << hb; }
  }
}
export function forEachAsc(b: Bits, fn: (i: number) => boolean | void): void {
  for (let w = 0; w < b.length; w++) {
    let x = b[w];
    while (x) { const t = x & -x; if (fn((w << 5) + (31 - Math.clz32(t))) === false) return; x ^= t; }
  }
}
