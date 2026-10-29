import * as duckdb from '@duckdb/duckdb-wasm';
const D = '/node_modules/@duckdb/duckdb-wasm/dist/';
window.init = async (base) => {
  const worker = new Worker(D + 'duckdb-browser-eh.worker.js');
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(D + 'duckdb-eh.wasm'); await db.open({filesystem:{reliableHeadRequests:true, allowFullHTTPReads:false, forceFullHTTPReads:false}});
  const origin = location.origin;
  await db.registerFileURL('postings.parquet', origin + base + 'postings.parquet', duckdb.DuckDBDataProtocol.HTTP, true);
  await db.registerFileURL('docs.parquet', origin + base + 'docs.parquet', duckdb.DuckDBDataProtocol.HTTP, true);
  window.conn = await db.connect(); window.db = db; return true;
};
const rows = async (sql) => (await window.conn.query(sql)).toArray().map(r => r.toJSON());
window.rowsq = rows;
window.q = async ({words, phrase, substr, lo, hi, limit = 20}) => {
  const t0 = performance.now(); const inl = words.map(w => `'${w}'`).join(',');
  const rng = lo != null ? ` AND doc BETWEEN ${lo} AND ${hi}` : '';
  const need = phrase || substr;
  const cand = await rows(`SELECT doc FROM 'postings.parquet' WHERE term IN (${inl})${rng} GROUP BY doc HAVING count(*) = ${words.length} ORDER BY doc DESC LIMIT ${need ? 2000 : limit}`);
  const out = []; const ids = cand.map(r => Number(r.doc));
  for (let i = 0; i < ids.length && out.length < limit; i += 40) {
    const b = ids.slice(i, i + 40);
    const d = await rows(`SELECT id, ts, text FROM 'docs.parquet' WHERE id IN (${b.join(',')})` + (phrase ? ` AND contains(lower(regexp_replace(text,'[^\\p{L}\\p{N}]+',' ','g')), '${phrase}')` : substr ? ` AND contains(lower(text), '${substr}')` : '') + ' ORDER BY id DESC');
    out.push(...d);
  }
  return {n: Math.min(out.length, limit), cand: ids.length, ms: performance.now() - t0, first: out[0] && String(out[0].text).slice(0, 80)};
};
window.init2 = async () => {
  const worker = new Worker(D + 'duckdb-browser-eh.worker.js');
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(D + 'duckdb-eh.wasm'); await db.open({});
  window.conn = await db.connect(); window.db = db; return true;
};
