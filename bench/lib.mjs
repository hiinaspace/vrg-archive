import { chromium } from 'playwright-core'; import fs from 'node:fs'; import zlib from 'node:zlib';
export const QUERIES = {
  rare: ['yamada','curation','creepypasta','czechvr','seasick'],
  common: ['vrchat','game','anyone','headset','quest'],
  phrase: ['mic spam','public avatars','index controllers'],
  substring: ['wrld_'],
  date: ['vrchat'], // 2023
};
export const Y2023 = [1672531200, 1704067200];
export async function launch() { return chromium.launch({executablePath:'/usr/bin/google-chrome', args:['--no-sandbox']}); }
const brCache = {};
function wire(u, bytes) { // static code/html: brotli estimate of whole file (CDN compresses); data: as transferred
  if (/\.(js|wasm|html|css)$/.test(u)) { const f='.'+u; if (!brCache[f]) brCache[f]=zlib.brotliCompressSync(fs.readFileSync(f)).length; return {static:true, b: brCache[f], raw: fs.statSync(f).size}; }
  return {static:false, b: bytes};
}
export async function srv(p){ return (await fetch('http://127.0.0.1:8099/'+p)).json().catch(()=>null); }
// summarize server log: static asset wire bytes (each file once) vs data bytes and request count
export function summarize(log) {
  let stat=0, data=0, nreq=0, nstat=0; const seen=new Set(); const per={};
  for (const e of log) { const w=wire(e.url,e.bytes);
    if (w.static) { if (!seen.has(e.url)) { seen.add(e.url); stat+=w.b; nstat++; } }
    else { data+=w.b; nreq++; per[e.url]=(per[e.url]||0)+w.b; } }
  return {static_br:stat, data, data_reqs:nreq, static_files:nstat};
}
