// Post text -> HTML for result snippets and the detail panel (greentext, quotes, spoilers, links, highlights).
import { esc } from "./util";
import { tokensWithSpans } from "./tok";

const TOKEN = /(⁠>>\d+)|(?<!⁠)>>(\d+)|(\[\/?spoiler\])|(https?:\/\/[^\s<>"']+)|(wrld_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g;
export const WORLDSEARCH = "https://worldsearch.hiina.space/?world=";

function hlText(t: string, hl: Set<string>): string {
  if (!hl.size || !t) return esc(t);
  let out = "", pos = 0;
  for (const k of tokensWithSpans(t)) {
    if (!hl.has(k.t)) continue;
    out += esc(t.slice(pos, k.s)) + "<mark>" + esc(t.slice(k.s, k.e)) + "</mark>";
    pos = k.e;
  }
  return out + esc(t.slice(pos));
}

/** HTML for a body; `root` is the site root prefix for links (e.g. "./") */
export function bodyHtml(body: string, hl: Set<string>, root = "./"): string {
  let spoiler = false;
  return body.split("\n").map((line) => {
    const green = line.startsWith(">") && !line.startsWith(">>");
    let out = spoiler ? '<s class="sp">' : "", pos = 0;
    for (const m of line.matchAll(TOKEN)) {
      out += hlText(line.slice(pos, m.index), hl);
      pos = m.index! + m[0].length;
      if (m[1]) out += esc(m[1].slice(1));
      else if (m[2]) out += `<a class="ql" href="${root}p/?${m[2]}">&gt;&gt;${m[2]}</a>`;
      else if (m[3]) {
        if (m[3] === "[spoiler]") { if (!spoiler) out += '<s class="sp">'; spoiler = true; }
        else if (spoiler) { out += "</s>"; spoiler = false; } else out += esc(m[3]);
      } else if (m[4]) {
        let url = m[4], tail = "";
        while (url && ".,;:!?)]}'\"".includes(url[url.length - 1])) { tail = url[url.length - 1] + tail; url = url.slice(0, -1); }
        out += `<a href="${esc(url)}" rel="nofollow noopener noreferrer" target="_blank">${hlText(url, hl)}</a>${esc(tail)}`;
      } else out += `<a class="wr" href="${WORLDSEARCH}${m[5]}" rel="noopener" target="_blank">${m[5]}</a>`;
    }
    out += hlText(line.slice(pos), hl);
    if (spoiler) out += "</s>";
    return green ? `<span class="gt">${out}</span>` : out;
  }).join("<br>");
}

/** a ~maxLen character window of the body around the first highlighted token, cut at line-ish boundaries */
export function snippet(body: string, hl: Set<string>, maxLen = 320): string {
  if (body.length <= maxLen) return bodyHtml(body, hl);
  let first = -1;
  if (hl.size) for (const k of tokensWithSpans(body)) if (hl.has(k.t)) { first = k.s; break; }
  let start = first < 0 ? 0 : Math.max(0, first - 110);
  if (start > 0) { const nl = body.lastIndexOf("\n", start); if (nl >= 0 && start - nl < 90) start = nl + 1; else { const sp = body.indexOf(" ", start); if (sp >= 0 && sp - start < 20) start = sp + 1; } }
  let end = Math.min(body.length, start + maxLen);
  if (end < body.length) { const sp = body.lastIndexOf(" ", end); if (sp > start + maxLen * 0.6) end = sp; }
  // keep an open [spoiler] consistent: bodyHtml closes it at the end of the cut
  let cut = body.slice(start, end);
  const opens = (body.slice(0, start).match(/\[spoiler\]/g) || []).length - (body.slice(0, start).match(/\[\/spoiler\]/g) || []).length;
  if (opens > 0) cut = "[spoiler]" + cut;
  return (start > 0 ? '<span class="el">…</span>' : "") + bodyHtml(cut, hl) + (end < body.length ? '<span class="el">…</span>' : "");
}
