// Sidebar facets with include (+) / exclude (-) rows. A row is a query condition: clicking edits the query text,
// so the URL and the pills stay the single source of truth. Counts are over the whole current result set.
import { Engine, Facets, EXTS } from "./engine";
import { Pill, addCondition, flipPill, parseQuery, removePill } from "./query";
import { esc, fmt } from "./util";

type St = "inc" | "exc" | "";
interface FRow { id: string; label: string; cond: string; count: number; test: (p: Pill) => boolean; title?: string }

const REPLY_STOPS = [1, 3, 10, 25];
const fieldIs = (f: string, v: string) => (p: Pill) => p.kind === "field" && p.field === f && p.value.toLowerCase() === v.toLowerCase();

function threadLabel(subject: string): string {
  const m = /#\d+/.exec(subject);
  return m ? m[0] : subject.replace(/^\/vrg\/\s*-?\s*/, "").slice(0, 28);
}

export function createFacets(host: HTMLElement, eng: Engine, getQ: () => string, setQ: (q: string) => void) {
  let rows = new Map<string, FRow>();
  let showMoreDom = false, showMoreThr = false;
  let last: Facets | null = null;

  const state = (r: FRow): { st: St; pill: Pill | null } => {
    for (const p of parseQuery(getQ()).pills) if (r.test(p)) return { st: p.negated ? "exc" : "inc", pill: p };
    return { st: "", pill: null };
  };
  function frow(r: FRow, max: number): string {
    const { st } = state(r);
    const bar = Math.max(r.count ? 2 : 0, Math.round((r.count / Math.max(1, max)) * 100));
    return `<li class="frow ${st}" data-id="${esc(r.id)}"><button type="button" class="pm plus" data-act="inc" aria-pressed="${st === "inc"}" title="only ${esc(r.title ?? r.label)}">+</button>`
      + `<button type="button" class="pm minus" data-act="exc" aria-pressed="${st === "exc"}" title="hide ${esc(r.title ?? r.label)}">−</button>`
      + `<span class="fname" title="${esc(r.title ?? r.label)}">${esc(r.label)}</span><span class="fbar"><i style="width:${bar}%"></i></span><small>${fmt(r.count)}</small></li>`;
  }
  function section(title: string, rs: FRow[], extra = ""): string {
    if (!rs.length) return "";
    for (const r of rs) rows.set(r.id, r);
    const mx = Math.max(1, ...rs.map((r) => r.count));
    return `<section><h3>${esc(title)}</h3><ul class="flist">${rs.map((r) => frow(r, mx)).join("")}</ul>${extra}</section>`;
  }

  function render(f: Facets) {
    last = f;
    rows = new Map();
    const q = getQ();
    const pills = parseQuery(q).pills;
    const selected = (test: (p: Pill) => boolean) => pills.some(test);
    const keep = (r: FRow) => r.count > 0 || selected(r.test);
    let html = "";

    // thread (edition)
    const thr = eng.threads.map((t, i) => ({ t, c: f.thread[i] })).filter((x) => x.c > 0);
    thr.sort((a, b) => b.c - a.c);
    const tid = (t: { no: number; edition: number }) => String(t.edition || t.no);
    const sel = eng.threads.filter((t) => selected(fieldIs("thread", tid(t))));
    const tlist = thr.slice(0, showMoreThr ? 24 : 8).map((x) => x.t);
    for (const t of sel) if (!tlist.includes(t)) tlist.push(t);
    html += section("Thread", tlist.map((t) => ({ id: "thread:" + tid(t), label: threadLabel(t.subject), title: t.subject, cond: "thread:" + tid(t), count: f.thread[eng.threads.indexOf(t)], test: fieldIs("thread", tid(t)) })),
      thr.length > 8 ? `<button type="button" class="linkbtn" data-more="thr">${showMoreThr ? "fewer threads" : "more threads"}</button>` : "");

    html += section("Posts", [
      { id: "has:image", label: "has image", title: "posts with an image", cond: "has:image", count: f.image, test: fieldIs("has", "image") },
      { id: "op:yes", label: "OP only", title: "first posts of threads", cond: "op:yes", count: f.op, test: fieldIs("op", "yes") },
      { id: "has:link", label: "has link", cond: "has:link", count: f.link, test: fieldIs("has", "link") },
      { id: "has:greentext", label: "has greentext", cond: "has:greentext", count: f.green, test: fieldIs("has", "greentext") },
    ].filter(keep));

    html += section("File type", EXTS.slice(1, 6).map((e, i) => ({ id: "ext:" + e, label: e, title: "." + e + " files", cond: "ext:" + e, count: f.ext[i + 1], test: fieldIs("ext", e) })).filter(keep));

    html += section("Replies", REPLY_STOPS.map((n, i) => ({
      id: "replies:" + n, label: `${n}+ replies`, cond: `replies:>=${n}`, count: f.rep[i],
      test: (p: Pill) => p.kind === "num" && p.field === "replies" && p.value === `>=${n}`,
    })).filter(keep));

    const dom = f.domain.filter((d) => d[1] > 0 || selected(fieldIs("domain", d[0]))).sort((a, b) => b[1] - a[1]);
    const shown = dom.slice(0, showMoreDom ? 40 : 10);
    for (const d of dom) if (selected(fieldIs("domain", d[0])) && !shown.includes(d)) shown.push(d);
    html += section("Link domain", shown.map(([n, c]) => ({ id: "domain:" + n, label: n, cond: "domain:" + n, count: c, test: fieldIs("domain", n) })),
      dom.length > 10 ? `<button type="button" class="linkbtn" data-more="dom">${showMoreDom ? "fewer sites" : "more sites"}</button>` : "");

    host.innerHTML = html + `<p class="dim fnote">Counts cover every post matching the query and all filters.</p>`;
  }

  host.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    const more = t.closest("[data-more]") as HTMLElement | null;
    if (more) { if (more.dataset.more === "dom") showMoreDom = !showMoreDom; else showMoreThr = !showMoreThr; if (last) render(last); return; }
    const li = t.closest("li.frow") as HTMLElement | null;
    if (!li) return;
    const r = rows.get(li.dataset.id!);
    if (!r) return;
    const btn = t.closest("button.pm") as HTMLElement | null;
    const act = btn ? (btn.dataset.act as "inc" | "exc") : t.closest(".fname,.fbar,small") ? "inc" : null;
    if (!act) return;
    const q = getQ();
    const { st, pill } = state(r);
    if (pill && st === act) setQ(removePill(q, pill));
    else if (pill) setQ(flipPill(q, pill));
    else setQ(addCondition(q, (act === "exc" ? "-" : "") + r.cond));
  });
  return { render };
}
