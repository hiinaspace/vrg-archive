export const $ = <T extends HTMLElement>(s: string, root: ParentNode = document) => root.querySelector(s) as T;
export const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
export const fmt = (n: number) => n.toLocaleString("en-US");
export const lsGet = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
export const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* blocked */ } };
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const p2 = (n: number) => String(n).padStart(2, "0");
export const isoDate = (ts: number) => new Date(ts * 1000).toISOString().slice(0, 10);
export function dateTime(ts: number): string {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ${DAYS[d.getUTCDay()]} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())} UTC`;
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const monthLabel = (absDay: number) => { const d = new Date(absDay * 86400000); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const dayIso = (absDay: number) => new Date(absDay * 86400000).toISOString().slice(0, 10);

export const dateShort = (ts: number) => new Date(ts * 1000).toISOString().slice(0, 16).replace("T", " ");
