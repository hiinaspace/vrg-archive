// Byte-accounted access to the static data files. A `Store` is injected so tests can read from disk.
export interface Store {
  /** whole file, gunzipped when it starts with the gzip magic */
  bin(path: string): Promise<Uint8Array>;
  /** byte range of a file (identity encoding) */
  range(path: string, off: number, len: number): Promise<Uint8Array>;
  stats: { bytes: number; requests: number };
}

export async function gunzip(buf: Uint8Array): Promise<Uint8Array> {
  if (buf.length < 2 || buf[0] !== 0x1f || buf[1] !== 0x8b) return buf;
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([buf as BlobPart]).stream().pipeThrough(ds);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export class HttpStore implements Store {
  stats = { bytes: 0, requests: 0 };
  private whole = new Map<string, Promise<Uint8Array>>();
  constructor(public base: string) {}
  private url(p: string) { return new URL(p, this.base).href; }
  async bin(path: string): Promise<Uint8Array> {
    const r = await fetch(this.url(path));
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    const b = new Uint8Array(await r.arrayBuffer());
    this.stats.bytes += b.length;
    this.stats.requests++;
    return gunzip(b);
  }
  async range(path: string, off: number, len: number): Promise<Uint8Array> {
    const w = this.whole.get(path);
    if (w) return (await w).subarray(off, off + len);
    const r = await fetch(this.url(path), { headers: { Range: `bytes=${off}-${off + len - 1}` } });
    this.stats.requests++;
    if (r.status === 206) {
      const b = new Uint8Array(await r.arrayBuffer());
      this.stats.bytes += b.length;
      return b;
    }
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    // host ignored Range: keep the whole file and slice
    const p = r.arrayBuffer().then((x) => new Uint8Array(x));
    this.whole.set(path, p);
    const all = await p;
    this.stats.bytes += all.length;
    return all.subarray(off, off + len);
  }
}

export class Reader {
  p = 0;
  constructor(public b: Uint8Array) {}
  v(): number { let r = 0, s = 1, c: number; do { c = this.b[this.p++]; r += (c & 127) * s; s *= 128; } while (c & 128); return r; }
  u32(): number { const b = this.b, p = this.p; this.p += 4; return (b[p] | (b[p + 1] << 8) | (b[p + 2] << 16) | (b[p + 3] << 24)) >>> 0; }
  get eof() { return this.p >= this.b.length; }
}

const dec = new TextDecoder();
export const utf8 = (b: Uint8Array) => dec.decode(b);

/** memoise async work by key; resolved values are also readable synchronously */
export class Cache<T> {
  private m = new Map<string, Promise<T>>();
  private v = new Map<string, T>();
  get(key: string, make: () => Promise<T>): Promise<T> {
    let p = this.m.get(key);
    if (!p) {
      p = make();
      this.m.set(key, p);
      p.then((x) => { this.v.set(key, x); }, () => { this.m.delete(key); });
    }
    return p;
  }
  set(key: string, val: T) { this.m.set(key, Promise.resolve(val)); this.v.set(key, val); }
  peek(key: string): T | undefined { return this.v.get(key); }
  has(key: string) { return this.v.has(key); }
  /** keep at most n entries (oldest first) */
  trim(n: number) {
    while (this.m.size > n) { const k = this.m.keys().next().value as string; this.m.delete(k); this.v.delete(k); }
  }
}
