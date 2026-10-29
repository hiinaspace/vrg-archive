// Static search engine: evaluates the boolean query language over sharded postings + column files.
// Result sets are exact bitsets over doc ids (docs are ordered by time), so facet counts and time
// series are exact. Phrases are verified against text blocks (read with HTTP Range).
import * as B from "./bits";
import type { Bits } from "./bits";
import { Cache, Reader, Store, gunzip, utf8 } from "./data";
import { Node, parseQuery } from "./query";
import { CH_FILE, CH_GREEN, CH_NAME, CH_TRIP, fnv1a, greentext, tokens } from "./tok";

export const FLAG_OP = 8, FLAG_LINK = 16, FLAG_GREEN = 32, FLAG_SPOILER = 64;
export const EXTS = ["", "jpg", "png", "gif", "webm", "mp4", "other"];
/** a phrase/field query verifies at most this many text blocks automatically; beyond it counts are upper bounds */
export const BLOCK_CAP = 400;

export interface Manifest {
  N: number; BS: number; B: number; parts: [number, number][]; packs: { first: number; size: number }[]; stop: string[];
  avgdl: number; day0: number; ndays: number; nthreads: number; snapshot: number; domains: string[]; thumb_packs: number;
  perm_shift: number; q_buckets: number;
}
export interface ThreadRow { no: number; edition: number; nPosts: number; nImages: number; first: number; last: number; subject: string }
export interface Row {
  doc: number; no: number; time: number; body: string; name: string | null; trip: string | null; fname: string | null; ext: string | null;
  w: number; h: number; spoiler: boolean; th: number[] | null; thread: number; rep: number;
}
interface Shard { terms: Map<string, { df: number; off: number; len: number }>; body: Uint8Array }
interface Verifier { chan: string; toks: string[] }
interface Res { node: Node | null; must: Bits; may: Bits | null; kids?: Res[]; op?: "and" | "or" | "not" | "leaf"; vf?: Verifier; scoreToks?: string[]; ignored?: boolean }

export interface Buckets { kind: "month" | "week"; starts: number[]; days: number[] /* first absolute day of each bucket */; }
export interface Facets {
  total: number; thread: Int32Array; image: number; op: number; link: number; green: number; ext: number[]; rep: number[]; domain: [string, number][];
}
export interface Run {
  q: string; errors: string[]; base: Bits; bits: Bits; lo: number; hi: number; d0: number | null; d1: number | null; total: number;
  /** true when a phrase had too many candidates to verify: base/bits/total are upper bounds until paged */
  pending: boolean; pendingDocs: number; verifiedBlocks: number; hl: Set<string>; ignored: string[]; hasText: boolean; res: Res | null;
}

const dayOfIso = (s: string) => Math.floor(Date.parse(s + "T00:00:00Z") / 86400000);

export class Engine {
  m!: Manifest; N = 0;
  thr!: Uint16Array; flags!: Uint8Array; rep!: Uint8Array;
  threads: ThreadRow[] = [];
  dayStart!: Uint32Array;
  domNames: string[] = []; domDocs: Uint32Array[] = [];
  blockOffs!: Uint32Array;
  stop = new Set<string>();
  months!: Buckets; weeks!: Buckets;
  private shards = new Cache<Shard>();
  private blocks = new Cache<unknown[][]>();
  private qshards = new Cache<Map<number, Uint32Array>>();
  private bitsCache = new Map<string, Bits>();
  private all!: Bits;
  constructor(public store: Store) {}

  static async load(store: Store): Promise<Engine> {
    const e = new Engine(store);
    const [man, cols, days, thr, dom, offs] = await Promise.all([
      store.bin("manifest.json"), store.bin("cols.bin"), store.bin("days.bin"), store.bin("threads.bin"), store.bin("dom.bin"), store.bin("docs/blocks.bin"),
    ]);
    e.m = JSON.parse(utf8(man));
    const N = (e.N = e.m.N);
    e.stop = new Set(e.m.stop);
    const dv = new DataView(cols.buffer, cols.byteOffset, cols.byteLength);
    const n = dv.getUint32(0, true);
    if (n !== N) throw new Error("cols/manifest mismatch");
    const lo = cols.subarray(4, 4 + N), hi = cols.subarray(4 + N, 4 + 2 * N);
    e.thr = new Uint16Array(N);
    for (let i = 0; i < N; i++) e.thr[i] = lo[i] | (hi[i] << 8);
    e.flags = cols.subarray(4 + 2 * N, 4 + 3 * N);
    e.rep = cols.subarray(4 + 3 * N, 4 + 4 * N);
    e.dayStart = new Uint32Array(days.buffer.slice(days.byteOffset, days.byteOffset + days.byteLength));
    e.threads = (JSON.parse(utf8(thr)) as [number, number, number, number, number, number, string][]).map((r) => ({
      no: r[0], edition: r[1], nPosts: r[2], nImages: r[3], first: r[4], last: r[5], subject: r[6],
    }));
    e.blockOffs = new Uint32Array(offs.buffer.slice(offs.byteOffset, offs.byteOffset + offs.byteLength));
    // domains
    const r = new Reader(dom);
    const hl = r.u32();
    const hr = new Reader(dom.subarray(4, 4 + hl));
    const body = dom.subarray(4 + hl);
    const nd = hr.v();
    let off = 0;
    for (let i = 0; i < nd; i++) {
      const ln = hr.v(); const name = utf8(hr.b.subarray(hr.p, hr.p + ln)); hr.p += ln;
      const df = hr.v(), pl = hr.v();
      const br = new Reader(body.subarray(off, off + pl)); off += pl;
      const docs = new Uint32Array(df); let prev = -1;
      for (let k = 0; k < df; k++) { prev += br.v() + 1; docs[k] = prev; }
      e.domNames.push(name); e.domDocs.push(docs);
    }
    e.buildBuckets();
    e.all = B.full(N);
    return e;
  }

  // ------------------------------------------------------------------ time buckets
  private buildBuckets() {
    const { day0, ndays } = this.m;
    const month: Buckets = { kind: "month", starts: [], days: [] };
    const week: Buckets = { kind: "week", starts: [], days: [] };
    let lastM = -1, lastW = -1;
    for (let d = 0; d < ndays; d++) {
      const abs = day0 + d;
      const dt = new Date(abs * 86400000);
      const ym = dt.getUTCFullYear() * 12 + dt.getUTCMonth();
      if (ym !== lastM) { month.starts.push(this.dayStart[d]); month.days.push(abs); lastM = ym; }
      const wk = Math.floor((abs + 3) / 7);
      if (wk !== lastW) { week.starts.push(this.dayStart[d]); week.days.push(abs); lastW = wk; }
    }
    month.starts.push(this.N); week.starts.push(this.N);
    this.months = month; this.weeks = week;
  }
  /** buckets restricted to those intersecting absolute days [d0, d1] */
  bucketsIn(kind: "month" | "week", d0: number, d1: number): Buckets {
    const src = kind === "month" ? this.months : this.weeks;
    const n = src.days.length;
    let a = 0;
    while (a + 1 < n && src.days[a + 1] <= d0) a++;
    let b = a;
    while (b + 1 < n && src.days[b + 1] <= d1) b++;
    return { kind, starts: src.starts.slice(a, b + 2), days: src.days.slice(a, b + 1) };
  }
  /** doc-id range [lo, hi) for absolute days [d0, d1] inclusive (null = open) */
  docRange(d0: number | null, d1: number | null): [number, number] {
    const nd = this.m.ndays, c = (x: number) => Math.max(0, Math.min(nd, x));
    const lo = d0 === null ? 0 : this.dayStart[c(d0 - this.m.day0)];
    const hi = d1 === null ? this.N : this.dayStart[c(d1 - this.m.day0 + 1)];
    return [lo, hi];
  }
  /** per-bucket count of all published posts */
  totals(bk: Buckets): number[] { return bk.days.map((_, i) => bk.starts[i + 1] - bk.starts[i]); }
  seriesCounts(bits: Bits, bk: Buckets): number[] { return bk.days.map((_, i) => B.countRange(bits, bk.starts[i], bk.starts[i + 1])); }

  // ------------------------------------------------------------------ postings
  private shard(part: number, bucket: number): Promise<Shard> {
    return this.shards.get(`${part}/${bucket}`, async () => {
      const buf = await this.store.bin(`idx/p${part}/${bucket}.bin`);
      const hl = new Reader(buf).u32();
      const r = new Reader(buf.subarray(4, 4 + hl));
      const n = r.v(); const terms = new Map<string, { df: number; off: number; len: number }>();
      let off = 0;
      for (let i = 0; i < n; i++) {
        const ln = r.v(); const t = utf8(r.b.subarray(r.p, r.p + ln)); r.p += ln;
        const df = r.v(), len = r.v();
        terms.set(t, { df, off, len }); off += len;
      }
      return { terms, body: buf.subarray(4 + hl) };
    });
  }
  /** ascending doc ids and packed (tf,len) bytes of a term across partitions */
  async postings(term: string): Promise<{ docs: Int32Array; low: Uint8Array }> {
    const b = fnv1a(term) % this.m.B;
    const sh = await Promise.all(this.m.parts.map((_, p) => this.shard(p, b).catch(() => null)));
    const chunks: { docs: Int32Array; low: Uint8Array }[] = [];
    let total = 0;
    sh.forEach((s, p) => {
      const ent = s?.terms.get(term);
      if (!s || !ent) return;
      const r = new Reader(s.body.subarray(ent.off, ent.off + ent.len));
      const docs = new Int32Array(ent.df), low = new Uint8Array(ent.df);
      let prev = this.m.parts[p][0] - 1;
      for (let i = 0; i < ent.df; i++) {
        const v = r.v(); const l = v % 64;
        prev += (v - l) / 64 + 1; docs[i] = prev; low[i] = l;
      }
      chunks.push({ docs, low }); total += ent.df;
    });
    if (chunks.length === 1) return chunks[0];
    const docs = new Int32Array(total), low = new Uint8Array(total); let o = 0;
    for (const c of chunks) { docs.set(c.docs, o); low.set(c.low, o); o += c.docs.length; }
    return { docs, low };
  }
  private async termBits(term: string): Promise<Bits> {
    const { docs } = await this.postings(term);
    const b = B.mkBits(this.N);
    for (let i = 0; i < docs.length; i++) B.setBit(b, docs[i]);
    return b;
  }

  // ------------------------------------------------------------------ text blocks
  private async fetchBlocks(list: number[]): Promise<void> {
    const need = [...new Set(list)].filter((b) => !this.blocks.has(String(b))).sort((a, b) => a - b);
    if (!need.length) return;
    const { packs } = this.m;
    const packOf = (b: number) => { let k = packs.length - 1; while (packs[k].first > b) k--; return k; };
    const span = (b: number) => {
      const k = packOf(b), off = this.blockOffs[b];
      const end = b + 1 < this.blockOffs.length && (k + 1 >= packs.length || b + 1 < packs[k + 1].first) ? this.blockOffs[b + 1] : packs[k].size;
      return { k, off, end };
    };
    // merge runs whose byte gap is small into single Range requests
    const runs: { k: number; off: number; end: number; bs: number[] }[] = [];
    for (const b of need) {
      const s = span(b);
      const last = runs[runs.length - 1];
      if (last && last.k === s.k && s.off - last.end <= 6000) { last.end = s.end; last.bs.push(b); }
      else runs.push({ k: s.k, off: s.off, end: s.end, bs: [b] });
    }
    await Promise.all(runs.map(async (run) => {
      const buf = await this.store.range(`docs/pack${run.k}.bin`, run.off, run.end - run.off);
      for (const b of run.bs) {
        const s = span(b);
        const rows = JSON.parse(utf8(await gunzip(buf.subarray(s.off - run.off, s.end - run.off)))) as unknown[][];
        this.blocks.set(String(b), rows);
      }
    }));
    this.blocks.trim(1500);
  }
  private cachedRows(doc: number): unknown[] | null {
    const p = this.blocks.peek(String(Math.floor(doc / this.m.BS)));
    return p ? p[doc % this.m.BS] : null;
  }
  async rows(docs: number[]): Promise<Row[]> {
    await this.fetchBlocks(docs.map((d) => Math.floor(d / this.m.BS)));
    return docs.map((d) => this.toRow(d, this.cachedRows(d)!));
  }
  private toRow(doc: number, r: unknown[]): Row {
    return {
      doc, no: r[0] as number, time: r[1] as number, body: r[2] as string, name: (r[3] as string) ?? null, trip: (r[4] as string) ?? null,
      fname: (r[5] as string) ?? null, ext: (r[6] as string) ?? null, w: (r[7] as number) ?? 0, h: (r[8] as number) ?? 0,
      spoiler: !!r[9], th: Array.isArray(r[10]) ? (r[10] as number[]) : null, thread: this.thr[doc], rep: this.rep[doc],
    };
  }

  // ------------------------------------------------------------------ evaluation
  private scan(key: string, pred: (i: number) => boolean): Bits {
    let b = this.bitsCache.get(key);
    if (!b) {
      b = B.mkBits(this.N);
      for (let i = 0; i < this.N; i++) if (pred(i)) B.setBit(b, i);
      this.bitsCache.set(key, b);
    }
    return b;
  }
  private threadBits(value: string): Bits {
    const v = value.trim().toLowerCase();
    const num = /^#?(\d+)$/.exec(v);
    const ok = new Uint8Array(this.threads.length);
    this.threads.forEach((t, i) => {
      if (num ? t.no === +num[1] || t.edition === +num[1] : t.subject.toLowerCase().includes(v)) ok[i] = 1;
    });
    return this.scan("thread:" + v, (i) => ok[this.thr[i]] === 1);
  }
  private async replyBits(no: number): Promise<Bits> {
    const qb = this.m.q_buckets, k = no % qb;
    const map = await this.qshards.get(String(k), async () => {
      const m = new Map<number, Uint32Array>();
      try {
        const buf = await this.store.bin(`q/${k}.bin`);
        const r = new Reader(buf); let to = 0;
        while (!r.eof) {
          to += r.v(); const n = r.v(); const a = new Uint32Array(n); let prev = -1;
          for (let i = 0; i < n; i++) { prev += r.v() + 1; a[i] = prev; }
          m.set(to, a);
        }
      } catch { /* no shard = no replies */ }
      return m;
    });
    const b = B.mkBits(this.N);
    for (const d of map.get(no) ?? []) B.setBit(b, d);
    return b;
  }
  private async textLeaf(chan: string, text: string, node: Node): Promise<Res> {
    const toks = tokens(text);
    if (!toks.length) return { node, must: this.all, may: null, ignored: true, op: "leaf" };
    const T = toks.map((t) => chan + t);
    let cand = chan === "" ? T.filter((t) => !this.stop.has(t)) : T;
    if (!cand.length) cand = T;
    cand = [...new Set(cand)];
    const sets = await Promise.all(cand.map((t) => this.termBits(t)));
    let bits = sets[0];
    for (let i = 1; i < sets.length; i++) bits = B.and(bits, sets[i]);
    const r: Res = { node, must: bits, may: null, op: "leaf", scoreToks: cand };
    if (T.length >= 2) { r.may = bits; r.must = B.mkBits(this.N); r.vf = { chan, toks }; }
    return r;
  }
  private exactLeaf(node: Node, bits: Bits): Res { return { node, must: bits, may: null, op: "leaf" }; }

  private async evalNode(n: Node, errors: string[]): Promise<Res> {
    switch (n.t) {
      case "and": case "or": {
        let kids = n.c;
        const ignoredStops: Node[] = [];
        if (n.t === "and") {
          const isStop = (k: Node) => k.t === "term" && !k.phrase && (() => { const t = tokens(k.text); return t.length === 1 && this.stop.has(t[0]); })();
          if (kids.some((k) => !isStop(k))) { ignoredStops.push(...kids.filter(isStop)); kids = kids.filter((k) => !isStop(k)); }
        }
        const rs = await Promise.all(kids.map((k) => this.evalNode(k, errors)));
        const may = rs.some((r) => r.may);
        let must = rs[0].must, up = rs[0].may ?? rs[0].must;
        for (let i = 1; i < rs.length; i++) {
          const o = rs[i];
          must = n.t === "and" ? B.and(must, o.must) : B.or(must, o.must);
          up = n.t === "and" ? B.and(up, o.may ?? o.must) : B.or(up, o.may ?? o.must);
        }
        const res: Res = { node: n, must, may: may ? up : null, kids: rs, op: n.t };
        (res as Res & { ignoredStops?: Node[] }).ignoredStops = ignoredStops;
        return res;
      }
      case "not": {
        const c = await this.evalNode(n.c, errors);
        return { node: n, must: B.not(c.may ?? c.must, this.N), may: c.may ? B.not(c.must, this.N) : null, kids: [c], op: "not" };
      }
      case "term": {
        if (!n.phrase) {
          const m = /^>>(\d+)$/.exec(n.text.trim());
          if (m) return this.exactLeaf(n, await this.replyBits(+m[1]));
        }
        return this.textLeaf("", n.text, n);
      }
      case "num": {
        const lo = n.lo === null ? 0 : n.loEx ? n.lo + 1 : n.lo, hi = n.hi === null ? 1e9 : n.hiEx ? n.hi - 1 : n.hi;
        return this.exactLeaf(n, this.scan(`rep:${lo}:${hi}`, (i) => this.rep[i] >= lo && this.rep[i] <= hi));
      }
      case "date": {
        const [lo, hi] = this.docRange(n.lo ? dayOfIso(n.lo) : null, n.hi ? dayOfIso(n.hi) : null);
        return this.exactLeaf(n, B.range(this.N, lo, hi));
      }
      case "field": {
        const v = n.value;
        switch (n.field) {
          case "thread": return this.exactLeaf(n, this.threadBits(v));
          case "name": return this.textLeaf(CH_NAME, v, n);
          case "filename": return this.textLeaf(CH_FILE, v, n);
          case "greentext": return this.textLeaf(CH_GREEN, v, n);
          case "trip": {
            const t = v.toLowerCase().replace(/^!+/, "");
            return { node: n, must: await this.termBits(CH_TRIP + t), may: null, op: "leaf" };
          }
          case "domain": {
            const d = v.toLowerCase().replace(/^www\./, "");
            const i = this.domNames.indexOf(d);
            if (i < 0) errors.push(`domain "${v}" is not one of the indexed sites (${this.domNames.slice(0, 8).join(", ")}, ...)`);
            const b = B.mkBits(this.N);
            if (i >= 0) for (const x of this.domDocs[i]) B.setBit(b, x);
            return this.exactLeaf(n, b);
          }
          case "has":
            return this.exactLeaf(n, v === "image" ? this.scan("has:image", (i) => (this.flags[i] & 7) !== 0)
              : v === "link" ? this.scan("has:link", (i) => (this.flags[i] & FLAG_LINK) !== 0) : this.scan("has:green", (i) => (this.flags[i] & FLAG_GREEN) !== 0));
          case "ext": { const c = EXTS.indexOf(v); return this.exactLeaf(n, this.scan("ext:" + v, (i) => (this.flags[i] & 7) === c)); }
          case "op": return this.exactLeaf(n, this.scan("op:" + v, (i) => ((this.flags[i] & FLAG_OP) !== 0) === (v === "yes")));
        }
      }
    }
    return this.exactLeaf(n, B.mkBits(this.N));
  }

  // ---- per-document truth for nodes that carry phrase verifiers
  private docTruth(r: Res, d: number, row: Row): boolean {
    if (r.vf) return !!r.may && B.hasBit(r.may, d) === 1 && this.verifies(r.vf, row);
    switch (r.op) {
      case "and": return r.kids!.every((k) => this.docTruth(k, d, row));
      case "or": return r.kids!.some((k) => this.docTruth(k, d, row));
      case "not": return !this.docTruth(r.kids![0], d, row);
      default: return !!B.hasBit(r.must, d);
    }
  }
  private verifies(v: Verifier, row: Row): boolean {
    const text = v.chan === CH_GREEN ? greentext(row.body) : v.chan === CH_FILE ? row.fname ?? "" : v.chan === CH_NAME ? row.name ?? "" : row.body;
    const hay = tokens(text), nd = v.toks;
    outer: for (let i = 0; i + nd.length <= hay.length; i++) {
      for (let j = 0; j < nd.length; j++) if (hay[i + j] !== nd[j]) continue outer;
      return true;
    }
    return false;
  }
  /** verify undecided docs; returns the subset that satisfies the whole query */
  private async verifyDocs(res: Res, docs: number[]): Promise<number[]> {
    await this.fetchBlocks(docs.map((d) => Math.floor(d / this.m.BS)));
    const out: number[] = [];
    for (const d of docs) {
      const row = this.toRow(d, this.cachedRows(d)!);
      if (this.docTruth(res, d, row)) out.push(d);
    }
    return out;
  }

  async run(q: string, opts: { exact?: boolean } = {}): Promise<Run> {
    const parsed = parseQuery(q);
    const errors = [...parsed.errors];
    const ast = parsed.ast;
    let lo = 0, hi = this.N;
    let d0: number | null = null, d1: number | null = null;
    const rest: Node[] = [];
    const top = !ast ? [] : ast.t === "and" ? ast.c : [ast];
    for (const k of top) {
      if (k.t === "date") {
        const [a, b] = this.docRange(k.lo ? dayOfIso(k.lo) : null, k.hi ? dayOfIso(k.hi) : null);
        lo = Math.max(lo, a); hi = Math.min(hi, b);
        if (k.lo) d0 = Math.max(d0 ?? -1e9, dayOfIso(k.lo));
        if (k.hi) d1 = Math.min(d1 ?? 1e9, dayOfIso(k.hi));
      } else rest.push(k);
    }
    const hl = new Set<string>();
    const ignored: string[] = [];
    let res: Res | null = null;
    let base = this.all;
    let pending = false, pendingDocs = 0, verifiedBlocks = 0;
    if (rest.length) {
      const root: Node = rest.length === 1 ? rest[0] : { t: "and", c: rest, start: 0, end: 0 };
      res = await this.evalNode(root, errors);
      collect(res, false, hl, ignored);
      base = res.must;
      if (res.may) {
        const und = B.andNot(res.may, res.must);
        const docs: number[] = [];
        B.forEach(und, (i) => { docs.push(i); });
        const nblocks = new Set(docs.map((d) => Math.floor(d / this.m.BS))).size;
        if (nblocks <= BLOCK_CAP || opts.exact) {
          const ok = await this.verifyDocs(res, docs);
          verifiedBlocks = nblocks;
          const add = B.mkBits(this.N);
          for (const d of ok) B.setBit(add, d);
          base = B.or(res.must, add);
          res = { ...res, must: base, may: null };
        } else {
          pending = true; pendingDocs = docs.length; base = res.may;
        }
      }
    }
    const bits = lo === 0 && hi === this.N ? base : B.and(base, B.range(this.N, lo, hi));
    return {
      q, errors, base, bits, lo, hi, d0, d1, total: B.count(bits), pending, pendingDocs, verifiedBlocks, hl, ignored,
      hasText: hl.size > 0, res,
    };
  }

  // ------------------------------------------------------------------ results
  /** docs of the current result in display order, verifying pending candidates lazily */
  async page(run: Run, sort: "newest" | "oldest" | "relevance" | "replied", offset: number, limit: number): Promise<{ docs: number[]; more: boolean }> {
    const need = offset + limit + 1;
    if (sort === "relevance") await this.prepareScores(run);
    let k = need * (run.pending ? 4 : 1);
    for (;;) {
      let cand = this.top(run, sort, k);
      const complete = cand.length < k;
      if (run.pending && run.res) {
        const known = run.res.must;
        const und = cand.filter((d) => !B.hasBit(known, d));
        const ok = new Set(await this.verifyDocs(run.res, und));
        cand = cand.filter((d) => B.hasBit(known, d) || ok.has(d));
      }
      if (cand.length >= need || complete) return { docs: cand.slice(offset, offset + limit), more: cand.length > offset + limit || (!complete && run.pending) };
      k *= 4;
    }
  }
  private top(run: Run, sort: "newest" | "oldest" | "relevance" | "replied", k: number): number[] {
    const bits = run.bits, out: number[] = [];
    if (sort === "oldest") { B.forEachAsc(bits, (i) => { out.push(i); return out.length < k; }); return out; }
    if (sort === "replied") {
      const hist = new Int32Array(256);
      B.forEach(bits, (i) => { hist[this.rep[i]]++; });
      let acc = 0, thr = 255;
      for (; thr > 0; thr--) { acc += hist[thr]; if (acc >= k) break; }
      const c: number[] = [];
      B.forEach(bits, (i) => { if (this.rep[i] >= thr) c.push(i); });
      c.sort((a, b) => this.rep[b] - this.rep[a] || b - a);
      return c.slice(0, k);
    }
    if (sort === "relevance" && run.res && run.hasText) {
      const sc = this.scores(run);
      let mx = 0;
      B.forEach(bits, (i) => { if (sc[i] > mx) mx = sc[i]; });
      const bins = new Int32Array(1025);
      B.forEach(bits, (i) => { bins[Math.floor((sc[i] / (mx || 1)) * 1024)]++; });
      let acc = 0, tb = 1024;
      for (; tb > 0; tb--) { acc += bins[tb]; if (acc >= k) break; }
      const c: number[] = [];
      B.forEach(bits, (i) => { if (Math.floor((sc[i] / (mx || 1)) * 1024) >= tb) c.push(i); });
      c.sort((a, b) => sc[b] - sc[a] || b - a);
      return c.slice(0, k);
    }
    B.forEachDesc(bits, (i) => { out.push(i); return out.length < k; });
    return out;
  }
  private scoresFor = new WeakMap<Run, Float32Array>();
  private scores(run: Run): Float32Array {
    let sc = this.scoresFor.get(run);
    if (sc) return sc;
    sc = new Float32Array(this.N);
    const toks = new Set<string>();
    gatherScoreToks(run.res!, false, toks);
    const { avgdl } = this.m;
    for (const t of toks) {
      const p = this.cachedPostings(t);
      if (!p) continue;
      const idf = Math.log(1 + (this.N - p.docs.length + 0.5) / (p.docs.length + 0.5));
      for (let i = 0; i < p.docs.length; i++) {
        const d = p.docs[i];
        if (!B.hasBit(run.bits, d)) continue;
        const tf = ((p.low[i] >> 4) & 3) + 1, lb = p.low[i] & 15;
        const L = Math.pow(2, lb / 1.6) - 1;
        const norm = 1.2 * (1 - 0.75 + (0.75 * L) / avgdl);
        sc[d] += (idf * tf * 2.2) / (tf + norm);
      }
    }
    this.scoresFor.set(run, sc);
    return sc;
  }
  private postCache = new Map<string, { docs: Int32Array; low: Uint8Array }>();
  private cachedPostings(t: string) { return this.postCache.get(t); }
  /** make sure postings used for scoring are decoded (shards are cached; this only decodes) */
  async prepareScores(run: Run) {
    if (!run.res) return;
    const toks = new Set<string>();
    gatherScoreToks(run.res, false, toks);
    await Promise.all([...toks].map(async (t) => { if (!this.postCache.has(t)) this.postCache.set(t, await this.postings(t)); }));
  }

  facets(run: Run): Facets {
    const bits = run.bits;
    const f: Facets = { total: run.total, thread: new Int32Array(this.threads.length), image: 0, op: 0, link: 0, green: 0, ext: [0, 0, 0, 0, 0, 0, 0], rep: [0, 0, 0, 0], domain: [] };
    B.forEach(bits, (i) => {
      f.thread[this.thr[i]]++;
      const fl = this.flags[i];
      const e = fl & 7;
      f.ext[e]++;
      if (e) f.image++;
      if (fl & FLAG_OP) f.op++;
      if (fl & FLAG_LINK) f.link++;
      if (fl & FLAG_GREEN) f.green++;
      const r = this.rep[i];
      if (r >= 1) { f.rep[0]++; if (r >= 3) { f.rep[1]++; if (r >= 10) { f.rep[2]++; if (r >= 25) f.rep[3]++; } } }
    });
    f.domain = this.domNames.map((n, j) => {
      let c = 0;
      for (const d of this.domDocs[j]) if (B.hasBit(bits, d)) c++;
      return [n, c] as [string, number];
    });
    return f;
  }
}

function collect(r: Res, neg: boolean, hl: Set<string>, ignored: string[]) {
  if (r.op === "not") { collect(r.kids![0], !neg, hl, ignored); return; }
  const ig = (r as Res & { ignoredStops?: Node[] }).ignoredStops;
  if (ig) for (const k of ig) if (k.t === "term") ignored.push(k.text);
  if (r.kids) for (const k of r.kids) collect(k, neg, hl, ignored);
  if (!neg && r.scoreToks) for (const t of r.scoreToks) hl.add(t.replace(/^[\u0001-\u0004]/, ""));
  if (!neg && r.vf) for (const t of r.vf.toks) hl.add(t);
}
function gatherScoreToks(r: Res, neg: boolean, out: Set<string>) {
  if (r.op === "not") return;
  if (r.kids) for (const k of r.kids) gatherScoreToks(k, neg, out);
  if (r.scoreToks) for (const t of r.scoreToks) out.add(t);
}
