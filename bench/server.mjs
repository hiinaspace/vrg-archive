// Range-logging static server. GET /__reset clears log, GET /__log returns it.
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
const root = path.resolve('.'); let log = [];
const types = {'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.wasm':'application/wasm','.json':'application/json'};
http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]);
  if (u === '/__reset') { log = []; return res.end('ok'); }
  if (u === '/__log') { res.setHeader('content-type','application/json'); return res.end(JSON.stringify(log)); }
  const f = path.join(root, u);
  if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { log.push({url: u, range: 'NOTFOUND ' + req.url, bytes: 0, code: 404}); res.statusCode = 404; return res.end('nf'); }
  const size = fs.statSync(f).size; const h = {'accept-ranges':'bytes','content-type':types[path.extname(f)]||'application/octet-stream','access-control-allow-origin':'*','cache-control':'no-store','etag':'"x"','last-modified':'Thu, 01 Jan 2026 00:00:00 GMT','access-control-expose-headers':'*','cross-origin-resource-policy':'cross-origin'};
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
  let s = 0, e = size - 1, code = 200;
  if (m) { code = 206; if (m[1] === '') { s = size - +m[2]; } else { s = +m[1]; if (m[2] !== '') e = Math.min(+m[2], size-1); } h['content-range'] = `bytes ${s}-${e}/${size}`; }
  h['content-length'] = e - s + 1;
  if (req.method === 'HEAD') { log.push({url: u, range: 'HEAD ' + (req.headers.range||''), bytes: 0, code}); res.writeHead(code, h); return res.end(); }
  const ent = {url: u, range: req.headers.range || null, bytes: 0, code}; log.push(ent);
  res.writeHead(code, h); const rs = fs.createReadStream(f, {start: s, end: e}); rs.on('data', d => { ent.bytes += d.length; }); res.on('close', () => rs.destroy()); if (!m && size > 1e6) { // throttle unranged big bodies so client aborts are visible in the byte count
    rs.on('data', d => { rs.pause(); setTimeout(() => rs.resume(), 5); res.write(d); }); rs.on('end', () => res.end());
  } else rs.pipe(res);
}).listen(8099, '127.0.0.1');
