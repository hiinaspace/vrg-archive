import { createDbWorker } from 'sql.js-httpvfs';
window.init = async (cfg) => {
  const w = await createDbWorker([{from:'jsonconfig', configUrl: cfg}], '/web/sqlite.worker.js', '/web/sql-wasm.wasm');
  window.w = w; return true;
};
window.q = async (sql, params) => { const t = performance.now(); const r = await window.w.db.query(sql, params); return {n: r.length, ms: performance.now()-t, first: r[0] && String(r[0].text||'').slice(0,80)}; };
