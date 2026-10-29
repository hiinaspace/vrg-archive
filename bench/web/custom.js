// Client for the custom sharded inverted index. No dependencies.
let M, base, offsets = null; const shardCache = new Map(); let stats;
const gunzip = async (buf) => new Uint8Array(await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
const fnv = (s) => { let h = 0x811c9dc5; for (const b of new TextEncoder().encode(s)) h = Math.imul(h ^ b, 0x01000193) >>> 0; return h; };
const tokens = (s) => (s.normalize('NFKC').toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
function rv(a, p) { let r = 0, s = 0, b; do { b = a[p.i++]; r += (b & 0x7f) * 2 ** s; s += 7; } while (b & 0x80); return r; }
export async function init(b) { base = b; M = await (await fetch(base + 'manifest.json')).json(); M.stopSet = new Set(M.stop); window.M = M; return true; }
async function shard(p, term) {
  const b = fnv(term) % M.B, key = p + '/' + b;
  if (!shardCache.has(key)) shardCache.set(key, (async () => {
    const r = await fetch(`${base}idx/p${p}/${b}.bin`); if (!r.ok) return null;
    const a = await gunzip(await r.arrayBuffer()); const dv = new DataView(a.buffer, a.byteOffset);
    const hl = dv.getUint32(0, true); const pos = { i: 4 }; const n = rv(a, pos); const ent = new Map(); let off = 4 + hl;
    const dec = new TextDecoder();
    for (let k = 0; k < n; k++) { const l = rv(a, pos); const t = dec.decode(a.subarray(pos.i, pos.i + l)); pos.i += l; const df = rv(a, pos); const len = rv(a, pos); ent.set(t, {df, off, len}); off += len; }
    return {a, ent};
  })());
  const s = await shardCache.get(key); return s && s.ent.has(term) ? {a: s.a, ...s.ent.get(term)} : null;
}
function decodePosts(e, p) { const lo = p * M.PS; let prev = lo - 1; const pos = { i: e.off }; const out = []; const end = e.off + e.len;
  while (pos.i < end) { const v = rv(e.a, pos); const d = Math.floor(v / 64); const low = v % 64; prev += d + 1; out.push([prev, low]); } return out; }
function monthStart(ts) { const d = new Date(ts * 1000); return d.getUTCFullYear() * 12 + d.getUTCMonth(); }
export function idRange(tsLo, tsHi) { // coarse month granularity from manifest
  if (tsLo == null) return [0, M.N - 1]; const a = monthStart(tsLo), b = monthStart(tsHi - 1); let lo = 0, hi = M.N - 1;
  for (let k = 0; k < M.months.length; k++) { const [m, id] = M.months[k]; if (m >= a && lo === 0) lo = id; if (m > b) { hi = id - 1; break; } }
  for (const [m, id] of M.months) if (m >= a) { lo = id; break; } return [lo, hi]; }
let offP; function loadOffsets() { return offP ||= loadOffsets0(); }
async function loadOffsets0() { const r = await fetch(base + M.offsets); const a = await gunzip(await r.arrayBuffer()); const pos = { i: 0 }; offsets = []; while (pos.i < a.length) offsets.push(rv(a, pos)); }
const blockCache = new Map();
async function block(bi) {
  if (!blockCache.has(bi)) blockCache.set(bi, (async () => {
    await loadOffsets(); let k = M.packs.length - 1; while (M.packs[k].first > bi) k--; const pk = M.packs[k];
    const start = offsets[bi]; const nextIdx = bi + 1; const end = (nextIdx < offsets.length && (k === M.packs.length - 1 || nextIdx < M.packs[k + 1].first)) ? offsets[nextIdx] : pk.size;
    const r = await fetch(base + pk.file, { headers: { Range: `bytes=${start}-${end - 1}` } });
    const a = await gunzip(await r.arrayBuffer()); return JSON.parse(new TextDecoder().decode(a)); })());
  return blockCache.get(bi);
}
async function getDocs(ids) { const m = new Map(); await Promise.all([...new Set(ids.map(i => Math.floor(i / M.BS)))].map(async bi => { const rows = await block(bi); rows.forEach((r, j) => m.set(bi * M.BS + j, r)); })); return m; }
// q: {words:[..], phrase:string|null, substr:string|null, sort:'rel'|'new', lo, hi, limit}
export async function query(q) {
  const t0 = performance.now(); const limit = q.limit || 20;
  const [lo, hi] = [q.lo ?? 0, q.hi ?? M.N - 1];
  let terms = [...new Set(q.words.flatMap(tokens))]; let ret = terms.filter(t => !M.stopSet.has(t)); if (!ret.length) ret = terms;
  const pl = []; for (let p = 0; p < M.parts; p++) if ((p + 1) * M.PS - 1 >= lo && p * M.PS <= hi) pl.push(p);
  if (q.sort === 'new') pl.reverse();
  const results = []; let candCount = 0;
  const verify = (txt) => { const l = txt.toLowerCase();
    if (q.phrase) return tokens(txt).join(' ').includes(tokens(q.phrase).join(' '));
    if (q.substr) return l.includes(q.substr.toLowerCase()); return true; };
  const needText = !!(q.phrase || q.substr);
  for (const p of pl) {
    const lists = await Promise.all(ret.map(async t => { const e = await shard(p, t); return e ? decodePosts(e, p).map(x => x).filter(x => x[0] >= lo && x[0] <= hi).map(x => [x[0], x[1], e.df]) : []; }));
    if (lists.some(l => !l.length)) continue;
    // intersect (sorted by id)
    lists.sort((a, b) => a.length - b.length); let cur = lists[0].map(x => ({id: x[0], s: score(x)}));
    for (let k = 1; k < lists.length; k++) { const m = new Map(lists[k].map(x => [x[0], x])); cur = cur.flatMap(c => { const y = m.get(c.id); return y ? [{id: c.id, s: c.s + score(y)}] : []; }); }
    candCount += cur.length;
    if (q.sort === 'new') {
      cur.sort((a, b) => b.id - a.id);
      for (let i = 0; i < cur.length && results.length < limit; i += 40) { const batch = cur.slice(i, i + 40); const d = await getDocs(batch.map(c => c.id)); for (const c of batch) { const r = d.get(c.id); if (!needText || verify(r[2])) { results.push({id: c.id, r}); if (results.length >= limit) break; } } }
      if (results.length >= limit) break;
    } else results.push(...cur.map(c => ({id: c.id, s: c.s})));
  }
  let out = results;
  if (q.sort !== 'new') {
    out.sort((a, b) => b.s - a.s); const fin = [];
    for (let i = 0; i < out.length && fin.length < limit; i += 40) { const batch = out.slice(i, i + 40); const d = await getDocs(batch.map(c => c.id)); for (const c of batch) { const r = d.get(c.id); if (!needText || verify(r[2])) { fin.push({id: c.id, r}); if (fin.length >= limit) break; } } }
    out = fin;
  }
  return { n: out.length, cand: candCount, ms: performance.now() - t0, first: out[0] && out[0].r[2].slice(0, 80) };
  function score(x) { const tf = (x[1] >> 4) + 1, lb = x[1] & 15; const dl = Math.pow(2, lb / 1.6) - 1; const df = x[2] * M.parts; const idf = Math.log(1 + (M.N - df + .5) / (df + .5)); return idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * dl / M.avgdl)); }
}
