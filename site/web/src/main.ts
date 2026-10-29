import "./style.css";
import { Engine, Row, Run } from "./engine";
import { HttpStore } from "./data";
import { Thumbs } from "./thumbs";
import { bodyHtml, snippet } from "./render";
import { COLORS, SeriesData, bucketRange, colorOf, createChart } from "./chart";
import { createFacets } from "./facets";
import { createPills, createSyntaxHelp } from "./pills";
import { State, SORTS, Sort, readUrl, toUrl } from "./state";
import { addCondition, parseQuery, relaxedQuery, removePill } from "./query";
import { $, dateShort, dateTime, esc, fmt } from "./util";

declare global { interface Window { vrg: any } }

const PAGE = 25;
const SORT_LABEL: Record<Sort, string> = { newest: "newest", oldest: "oldest", relevance: "relevance", replied: "most replied" };
const SORT_TIP: Record<Sort, string> = { newest: "newest first", oldest: "oldest first", relevance: "best text match (bm25-like)", replied: "most replies" };

const store = new HttpStore(new URL("data/", location.href).href);
let eng: Engine, thumbs: Thumbs;
let state: State = readUrl();
let cmpDraft: string[] = [...state.cmp];
let shown = PAGE, seq = 0;
let current: { run: Run; rows: Map<string, Row> } | null = null;
let chart: ReturnType<typeof createChart>;
let facets: ReturnType<typeof createFacets>;
let pills: ReturnType<typeof createPills>;

const setStatus = (t: string) => { $("#status").textContent = t; };

function commit(push = true) {
  const u = toUrl({ ...state, cmp: cmpDraft.filter(Boolean) });
  if (u !== location.pathname + location.search) (push ? history.pushState : history.replaceState).call(history, null, "", u);
}
let timer: ReturnType<typeof setTimeout>;
function change(debounce = 0, push = true) {
  state.cmp = cmpDraft.filter(Boolean);
  pills?.render();
  clearTimeout(timer);
  timer = setTimeout(() => { shown = PAGE; commit(push); void refresh(); }, debounce);
}
const setQ = (q: string) => { state.q = q; $<HTMLInputElement>("#q").value = q; change(); };

async function boot() {
  setStatus("loading index…");
  const t0 = performance.now();
  eng = await Engine.load(store);
  thumbs = new Thumbs(store);
  chart = createChart($("#chart"), onBrush);
  facets = createFacets($("#facets"), eng, () => state.q, setQ);
  pills = createPills($("#pills"), () => state.q, setQ);
  const q = $<HTMLInputElement>("#q");
  q.value = state.q;
  let typed = false, typedTimer: ReturnType<typeof setTimeout>;
  q.addEventListener("input", () => {
    state.q = q.value;
    change(150, !typed);
    typed = true; clearTimeout(typedTimer); typedTimer = setTimeout(() => (typed = false), 1200);
  });
  $("#qform").addEventListener("submit", (e) => { e.preventDefault(); change(); });
  createSyntaxHelp($("#syntax-btn"), $("#syntax-pop"), (ex) => setQ(addCondition(state.q, ex)));
  $("#mode").addEventListener("click", (e) => { const b = (e.target as HTMLElement).closest("button"); if (b) { state.mode = b.dataset.v as State["mode"]; commit(); void renderChartOnly(); } });
  $("#gran").addEventListener("click", (e) => { const b = (e.target as HTMLElement).closest("button"); if (b) { state.gran = b.dataset.v as State["gran"]; commit(); void renderChartOnly(); } });
  $("#sorts").addEventListener("click", (e) => { const b = (e.target as HTMLElement).closest("button[data-sort]") as HTMLElement | null; if (b) { state.sort = b.dataset.sort as Sort; change(); } });
  $("#more").addEventListener("click", () => { shown += PAGE; void refresh(false); });
  $("#fbtn").addEventListener("click", () => document.body.classList.toggle("drawer"));
  $("#legend").addEventListener("click", onLegend);
  $("#legend").addEventListener("change", onLegend);
  $("#results").addEventListener("click", onResultClick);
  $("#detail").addEventListener("click", onDetailClick);
  window.addEventListener("popstate", () => { state = readUrl(); cmpDraft = [...state.cmp]; q.value = state.q; pills.render(); void refresh(); });
  window.vrg = { eng, store, run: (s: string) => eng.run(s), search: (s: string) => { setQ(s); return lastDone; }, state: () => state };
  pills.render();
  await refresh();
  setStatus(`${fmt(eng.N)} posts · ready in ${Math.round(performance.now() - t0)} ms`);
}

let lastDone: Promise<void> = Promise.resolve();
function refresh(full = true): Promise<void> {
  lastDone = doRefresh(full);
  return lastDone;
}

async function doRefresh(full: boolean) {
  const my = ++seq;
  const t0 = performance.now();
  document.body.classList.remove("has-detail");
  renderSorts();
  renderModeButtons();
  const run = await eng.run(state.q);
  if (my !== seq) return;
  const pg = await eng.page(run, state.sort, 0, shown);
  if (my !== seq) return;
  const rows = await eng.rows(pg.docs);
  if (my !== seq) return;
  current = { run, rows: new Map(rows.map((r) => [String(r.no), r])) };
  const ms = Math.round(performance.now() - t0);
  const up = run.pending ? "≤ " : "";
  $("#summary").innerHTML = `${up}${fmt(run.total)} post${run.total === 1 ? "" : "s"} <span class="dim">· ${ms} ms · ${(store.stats.bytes / 1e6).toFixed(2)} MB fetched so far</span>`
    + (run.pending ? ` <span class="warn" title="Phrase candidates exceed the automatic verification limit; counts are upper bounds until verified.">approximate <button type="button" class="linkbtn" id="exact">make exact</button></span>` : "")
    + (run.ignored.length ? ` <span class="dim">· ignored common word${run.ignored.length > 1 ? "s" : ""}: ${esc(run.ignored.join(", "))}</span>` : "");
  const ex = document.getElementById("exact");
  if (ex) ex.onclick = async () => { ex.textContent = "verifying…"; const r2 = await eng.run(state.q, { exact: true }); current!.run = r2; void refresh(); };
  const relax = run.total < 5 ? relaxedQuery(state.q) : null;
  $("#results").innerHTML = (rows.length && relax ? `<li class="empty-state"><div>Only ${run.total} match all words. <button type="button" class="linkbtn" data-relax="${esc(relax)}">Match any all-but-one subset of the words instead</button></div></li>` : "") + (rows.length ? rows.map((r) => rowHtml(r, run)).join("") : `<li class="empty-state"><div><b>No posts match.</b><br>Remove a pill above, or relax a filter.${relax ? `<br><button type="button" class="linkbtn" data-relax="${esc(relax)}">Match any all-but-one subset of the words instead</button>` : ""}</div></li>`);
  hydrateThumbs($("#results"));
  ($("#more") as HTMLButtonElement).hidden = !pg.more;
  pills.render();
  facets.render(eng.facets(run));
  if (full) await renderChart(run, my);
  if (state.post && current.rows.has(state.post)) openDetail(state.post, false);
  const bytes = store.stats.bytes;
  setStatus(`${fmt(eng.N)} posts · ${ms} ms · ${(bytes / 1e6).toFixed(2)} MB`);
}

// ------------------------------------------------------------------ chart
async function chartParts(run: Run) {
  const dateRange: [number, number] | null = run.d0 !== null || run.d1 !== null ? [run.d0 ?? eng.m.day0, run.d1 ?? eng.m.day0 + eng.m.ndays - 1] : null;
  const span = dateRange ? dateRange[1] - dateRange[0] : Infinity;
  const kind = state.gran === "auto" ? (span <= 800 ? "week" : "month") : state.gran;
  let w0 = eng.m.day0, w1 = eng.m.day0 + eng.m.ndays - 1;
  if (dateRange) { const pad = Math.max(30, span); w0 = Math.max(w0, dateRange[0] - pad); w1 = Math.min(w1, dateRange[1] + pad); }
  const bk = eng.bucketsIn(kind, w0, w1);
  const totals = eng.totals(bk);
  const series: SeriesData[] = [{ label: state.q || "all posts", color: colorOf(0), counts: eng.seriesCounts(run.base, bk), approx: run.pending }];
  const cmps = await Promise.all(cmpDraft.map((q) => (q ? eng.run(q) : null)));
  cmps.forEach((r, i) => series.push(r ? { label: r.q, color: colorOf(i + 1), counts: eng.seriesCounts(r.bits, bk), approx: r.pending } : { label: "", color: colorOf(i + 1), counts: bk.days.map(() => 0), approx: false }));
  let brush: [number, number] | null = null;
  if (dateRange) {
    let a = bk.days.findIndex((_, i) => bk.starts[i + 1] > run.lo);
    let b = bk.days.length - 1;
    while (b > 0 && bk.starts[b] >= run.hi) b--;
    if (a < 0) a = 0;
    brush = [a, Math.max(a, b)];
  }
  return { bk, totals, series, brush };
}
let lastRun: Run | null = null;
async function renderChart(run: Run, my = seq) {
  lastRun = run;
  const p = await chartParts(run);
  if (my !== seq) return;
  chartBk = p.bk;
  chart.render({ ...p, mode: state.mode });
  const tot = p.series.map((s) => s.counts.reduce((a, b) => a + b, 0));
  $("#sinfo").textContent = `${p.bk.kind === "month" ? "per month" : "per week"} · ${state.mode === "share" ? "share of all posts that " + p.bk.kind : "post counts"}${tot.length ? "" : ""}`;
  renderLegend(p.series, tot);
}
let chartBk: ReturnType<Engine["bucketsIn"]> | null = null;
async function renderChartOnly() { renderModeButtons(); if (lastRun) await renderChart(lastRun); }
function renderModeButtons() {
  document.querySelectorAll<HTMLElement>("#mode button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.mode));
  document.querySelectorAll<HTMLElement>("#gran button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.gran));
}
function renderLegend(series: SeriesData[], tot: number[]) {
  const n = cmpDraft.length;
  let h = `<div class="lg"><i style="background:${series[0].color}"></i><span class="lq">search box</span><b>${fmt(tot[0])}</b><span class="dim"> matches in view</span></div>`;
  for (let i = 0; i < n; i++) {
    const s = series[i + 1];
    h += `<div class="lg" data-i="${i}"><i style="background:${colorOf(i + 1)}"></i><input class="cq" value="${esc(cmpDraft[i])}" placeholder="compare query, e.g. llm" aria-label="compare query ${i + 1}"><b>${s && cmpDraft[i] ? fmt(tot[i + 1]) : ""}</b>${s?.approx ? '<span class="warn">upper bound</span>' : ""}<button type="button" class="x" data-rm="${i}" aria-label="remove">×</button></div>`;
  }
  if (n < 5) h += `<button type="button" class="linkbtn" data-add="1">+ compare another query</button>`;
  const active = document.activeElement as HTMLElement | null;
  if (active?.classList.contains("cq")) return; // do not clobber a field being edited
  $("#legend").innerHTML = h;
  void COLORS;
}
function onLegend(e: Event) {
  const t = e.target as HTMLElement;
  if (e.type === "click") {
    if (t.dataset.add) { cmpDraft.push(""); void renderChartOnly().then(() => document.querySelectorAll<HTMLInputElement>(".cq")[cmpDraft.length - 1]?.focus()); return; }
    if (t.dataset.rm !== undefined) { cmpDraft.splice(+t.dataset.rm, 1); change(); }
  } else if (t.classList.contains("cq")) {
    const i = +(t.closest(".lg") as HTMLElement).dataset.i!;
    cmpDraft[i] = (t as HTMLInputElement).value.trim();
    (t as HTMLInputElement).blur();
    change();
  }
}
function onBrush(r: [number, number] | null) {
  let q = state.q;
  for (const p of parseQuery(q).pills) if (p.kind === "date" && !p.negated) q = removePill(q, p);
  if (r && chartBk) {
    const a = bucketRange(chartBk, r[0]), b = bucketRange(chartBk, r[1]);
    q = addCondition(q, a[0] === b[1] ? `date:${a[0]}` : `date:${a[0]}..${b[1]}`);
  }
  setQ(q);
}

// ------------------------------------------------------------------ rows
function sortLabel(): string { return SORT_LABEL[state.sort]; }
function renderSorts() {
  $("#sorts").innerHTML = `<span class="lbl">Sort</span>` + SORTS.map((x) => `<button type="button" data-sort="${x}" class="${x === state.sort ? "on" : ""}" aria-pressed="${x === state.sort}" title="${SORT_TIP[x]}">${SORT_LABEL[x]}</button>`).join("");
  void sortLabel;
}
function threadOf(r: Row) { return eng.threads[r.thread]; }
function thumbHtml(r: Row, big = false): string {
  if (!r.ext) return "";
  const sp = r.spoiler ? " sp" : "";
  const dims = r.w ? `${r.w}×${r.h}` : "";
  if (r.th) {
    return `<div class="thumb${sp}" data-th="${r.th.join(",")}" style="aspect-ratio:${r.th[3]}/${r.th[4]}"><span class="phn">${esc(r.fname ?? "")}${esc(r.ext)}</span></div>`;
  }
  void big;
  return `<div class="thumb ph${sp}" title="no thumbnail archived"><span class="phn">${esc(r.fname ?? "")}</span><span class="phe">${esc(r.ext)}</span>${dims ? `<span class="phd">${dims}</span>` : ""}</div>`;
}
function rowHtml(r: Row, run: Run): string {
  const t = threadOf(r);
  const href = `t/${t.no}.html#p${r.no}`;
  const tl = /#\d+/.exec(t.subject)?.[0] ?? t.subject;
  const who = r.name ? `<span class="nm">${esc(r.name)}</span>${r.trip ? ` <span class="tr">${esc(r.trip)}</span>` : ""} ` : "";
  return `<li data-no="${r.no}" tabindex="0">${thumbHtml(r)}<div class="rb">`
    + `<div class="l1">${who}<span class="date">${dateShort(r.time)}</span><a class="tlink" href="${href}" title="${esc(t.subject)}">${esc(tl)}</a><a class="no" href="${href}">No.${r.no}</a>`
    + (r.rep ? `<span class="reps" title="replies">${r.rep >= 255 ? "255+" : r.rep} ${r.rep === 1 ? "reply" : "replies"}</span>` : "") + `</div>`
    + `<div class="snip">${snippet(r.body, run.hl) || '<span class="dim">(no text)</span>'}</div>`
    + (r.ext && !r.th ? "" : "") + `</div></li>`;
}
function hydrateThumbs(root: HTMLElement) {
  root.querySelectorAll<HTMLElement>(".thumb[data-th]:not([data-done])").forEach((el) => {
    el.dataset.done = "1";
    const th = el.dataset.th!.split(",").map(Number);
    void thumbs.url(th).then((u) => {
      if (!u) return;
      const img = new Image(); img.alt = ""; img.src = u;
      el.textContent = ""; el.appendChild(img);
    });
  });
}
function onResultClick(e: Event) {
  const me = e as MouseEvent, t = e.target as HTMLElement;
  const rx = t.closest("[data-relax]") as HTMLElement | null;
  if (rx) { setQ(rx.dataset.relax!); return; }
  const sp = t.closest(".thumb.sp");
  if (sp) { sp.classList.toggle("rv"); e.preventDefault(); return; }
  if (t.closest("s.sp")) { t.closest("s.sp")!.classList.toggle("rv"); return; }
  if (t.closest("a") || me.ctrlKey || me.metaKey || window.getSelection()?.toString()) return;
  const li = t.closest("li[data-no]") as HTMLElement | null;
  if (li) openDetail(li.dataset.no!, true);
}

// ------------------------------------------------------------------ detail
function openDetail(no: string, push: boolean) {
  const r = current?.rows.get(no);
  if (!r || !current) return;
  state.post = no;
  if (push) commit(false);
  document.querySelectorAll("#results > li").forEach((li) => li.classList.toggle("sel", (li as HTMLElement).dataset.no === no));
  const t = threadOf(r);
  const d = $("#detail");
  d.hidden = false;
  document.body.classList.add("has-detail");
  d.innerHTML = `<div class="dhead"><button type="button" class="back" data-close>&larr; results</button><button type="button" class="x" data-close aria-label="close">×</button></div>`
    + (r.ext ? `<div class="dthumb">${thumbHtml(r, true)}</div>` : "")
    + `<h2>No.${r.no}</h2><p class="dim">${dateTime(r.time)}</p>`
    + `<div class="dbody">${bodyHtml(r.body, current.run.hl)}</div>`
    + (r.ext ? `<p class="dim">File: ${esc((r.fname ?? "") + r.ext)}${r.w ? ` (${r.w}×${r.h})` : ""}${r.th ? "" : " · no thumbnail archived"}</p>` : "")
    + `<table><tr><th>Thread</th><td><a href="t/${t.no}.html">${esc(t.subject)}</a></td></tr>`
    + `<tr><th>Replies</th><td>${r.rep}${r.rep ? ` <a href="?q=${encodeURIComponent(">>" + r.no)}" data-q="&gt;&gt;${r.no}">show</a>` : ""}</td></tr></table>`
    + `<p class="dact"><a class="primary" href="t/${t.no}.html#p${r.no}">Open in thread</a> <a href="p/?${r.no}">Permalink</a> `
    + `<a href="?q=${encodeURIComponent("thread:" + (t.edition || t.no))}" data-q="thread:${t.edition || t.no}">More from this thread</a></p>`;
  hydrateThumbs(d);
}
function onDetailClick(e: Event) {
  const t = e.target as HTMLElement;
  if (t.closest("[data-close]")) { state.post = ""; commit(false); $("#detail").hidden = true; document.body.classList.remove("has-detail"); document.querySelectorAll("#results > li.sel").forEach((l) => l.classList.remove("sel")); return; }
  const sp = t.closest(".thumb.sp, s.sp"); if (sp) { sp.classList.toggle("rv"); return; }
  const a = t.closest("a[data-q]") as HTMLElement | null;
  if (a) { e.preventDefault(); state.post = ""; setQ(a.dataset.q!.replace(/&gt;/g, ">")); }
}

boot().catch((e) => { console.error(e); setStatus("failed to load: " + String(e?.message ?? e)); });
