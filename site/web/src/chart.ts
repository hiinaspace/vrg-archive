// Over-time chart: one line per query (matches per month/week, as a count or as a share of all posts that
// month/week). Drag to brush a date range, click a bucket to pick it. Hover for exact numbers.
import { Buckets } from "./engine";
import { dayIso, esc, fmt, monthLabel } from "./util";

export interface SeriesData { label: string; color: string; counts: number[]; approx: boolean }
export interface ChartInput { bk: Buckets; totals: number[]; series: SeriesData[]; mode: "share" | "count"; brush: [number, number] | null }
export const COLORS = ["#3a3ac8", "#c25400", "#0b7a4b", "#c2185b", "#0a6aa8", "#7a5c00"];
const DARK_COLORS = ["#8b7dff", "#ffa940", "#3fd18f", "#ff6b9b", "#5b9bff", "#e8c547"];
const isDark = () => { const t = document.documentElement.dataset.theme; return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; };
export const colorOf = (i: number) => (isDark() ? DARK_COLORS : COLORS)[i % COLORS.length];

let W = 900;
const H = 210, L = 46, R = 8, T = 8, Bm = 22;

export function bucketLabel(bk: Buckets, i: number): string {
  return bk.kind === "month" ? monthLabel(bk.days[i]) : "week of " + dayIso(bk.days[i]);
}
export function bucketRange(bk: Buckets, i: number): [string, string] {
  if (bk.kind === "week") return [dayIso(bk.days[i]), dayIso(bk.days[i] + 6)];
  const a = dayIso(bk.days[i]);
  return [a.slice(0, 7), a.slice(0, 7)];
}

export function createChart(host: HTMLElement, onBrush: (r: [number, number] | null) => void) {
  host.innerHTML = `<div class="cwrap"><svg role="img" aria-label="matches over time"></svg><div class="ctip" hidden></div></div>`;
  const svg = host.querySelector("svg") as SVGSVGElement;
  const tip = host.querySelector(".ctip") as HTMLElement;
  let cur: ChartInput | null = null;
  let drag: { a: number; b: number } | null = null;

  const n = () => cur?.bk.days.length ?? 1;
  const xOf = (i: number) => L + ((i + 0.5) / n()) * (W - L - R);
  const bucketAt = (clientX: number) => {
    const r = svg.getBoundingClientRect();
    const x = ((clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(n() - 1, Math.floor(((x - L) / (W - L - R)) * n())));
  };
  const val = (c: number, t: number, mode: string) => (mode === "share" ? (t ? (c / t) * 100 : 0) : c);

  function draw() {
    if (!cur) return;
    W = Math.max(320, host.clientWidth || 900);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("height", String(H));
    const { bk, totals, series, mode } = cur;
    const vals = series.map((s) => s.counts.map((c, i) => val(c, totals[i], mode)));
    let mx = Math.max(1e-9, ...vals.map((v) => Math.max(0, ...v)));
    const nice = (x: number) => { const p = Math.pow(10, Math.floor(Math.log10(x))); const f = x / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };
    mx = nice(mx);
    const y = (v: number) => T + (1 - v / mx) * (H - T - Bm);
    let s = "";
    for (let k = 0; k <= 4; k++) {
      const v = (mx * k) / 4, yy = y(v);
      s += `<line class="gx" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/><text class="ax" x="${L - 4}" y="${yy + 3}" text-anchor="end">${mode === "share" ? (v < 1 ? v.toFixed(2) : v.toFixed(v < 10 ? 1 : 0)) + "%" : fmt(Math.round(v))}</text>`;
    }
    // x labels: each year (months) or each quarter-ish (weeks)
    let lastY = -1, lastLab = -1e9;
    bk.days.forEach((d, i) => {
      const dt = new Date(d * 86400000);
      const key = bk.kind === "month" ? dt.getUTCFullYear() : dt.getUTCFullYear() * 12 + Math.floor(dt.getUTCMonth() / 3);
      if (key !== lastY && (bk.kind === "week" ? i === 0 || dt.getUTCDate() <= 7 : dt.getUTCMonth() === 0 || i === 0)) {
        const px = xOf(i);
        if (px - lastLab > 34) {
          s += `<text class="ax" x="${px}" y="${H - 6}" text-anchor="middle">${bk.kind === "month" ? dt.getUTCFullYear() : dayIso(d).slice(0, 7)}</text>`;
          lastLab = px;
        }
        lastY = key;
      }
    });
    if (cur.brush) {
      const [a, b] = cur.brush;
      s += `<rect class="brush" x="${xOf(a) - (W - L - R) / n() / 2}" width="${((b - a + 1) * (W - L - R)) / n()}" y="${T}" height="${H - T - Bm}"/>`;
    }
    if (drag) {
      const a = Math.min(drag.a, drag.b), b = Math.max(drag.a, drag.b);
      s += `<rect class="brush live" x="${xOf(a) - (W - L - R) / n() / 2}" width="${((b - a + 1) * (W - L - R)) / n()}" y="${T}" height="${H - T - Bm}"/>`;
    }
    series.forEach((se, k) => {
      if (k > 0 && !se.label) return;
      const pts = vals[k].map((v, i) => `${xOf(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
      if (k === 0) s += `<polygon points="${xOf(0)},${y(0)} ${pts} ${xOf(n() - 1)},${y(0)}" fill="${se.color}" opacity=".16"/>`;
      s += `<polyline points="${pts}" fill="none" stroke="${se.color}" stroke-width="${k === 0 ? 2 : 1.6}" vector-effect="non-scaling-stroke"${se.approx ? ' stroke-dasharray="5 3"' : ""}/>`;
    });
    svg.innerHTML = s;
  }

  function showTip(i: number, clientX: number) {
    if (!cur) return;
    const { bk, totals, series, mode } = cur;
    const rows = series.filter((se, k) => k === 0 || se.label).map((se) => {
      const c = se.counts[i], t = totals[i];
      return `<div><i style="background:${se.color}"></i>${esc(se.label)}: <b>${fmt(c)}</b>${se.approx ? " (upper bound)" : ""} <span class="dim">${t ? ((c / t) * 100).toFixed(c / t < 0.01 ? 3 : 2) + "% of " + fmt(t) : "no posts"}</span></div>`;
    }).join("");
    tip.innerHTML = `<b>${esc(bucketLabel(bk, i))}</b>${rows}`;
    tip.hidden = false;
    const hr = host.getBoundingClientRect();
    const px = clientX - hr.left;
    tip.style.left = Math.min(Math.max(0, px + 12), hr.width - tip.offsetWidth - 4) + "px";
    void mode;
  }

  const wrap = host.querySelector(".cwrap") as HTMLElement;
  wrap.addEventListener("pointerdown", (e) => {
    if (!cur) return;
    wrap.setPointerCapture(e.pointerId);
    const b = bucketAt(e.clientX);
    drag = { a: b, b };
    e.preventDefault();
  });
  wrap.addEventListener("pointermove", (e) => {
    const b = bucketAt(e.clientX);
    if (drag) { drag.b = b; draw(); }
    showTip(b, e.clientX);
  });
  wrap.addEventListener("pointerleave", () => { tip.hidden = true; });
  const end = () => {
    if (!drag || !cur) return;
    const a = Math.min(drag.a, drag.b), b = Math.max(drag.a, drag.b), moved = drag.a !== drag.b;
    drag = null;
    const same = cur.brush && cur.brush[0] === a && cur.brush[1] === b;
    onBrush(same && !moved ? null : [a, b]);
    draw();
  };
  wrap.addEventListener("pointerup", end);
  wrap.addEventListener("pointercancel", () => { drag = null; draw(); });

  new ResizeObserver(() => draw()).observe(host);
  return { render(input: ChartInput) { cur = input; draw(); } };
}
