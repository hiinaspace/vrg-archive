// URL <-> UI state. Everything that defines a view lives in the URL so it can be shared.
export type Sort = "newest" | "oldest" | "relevance" | "replied";
export const SORTS: Sort[] = ["newest", "oldest", "relevance", "replied"];
export type Gran = "auto" | "month" | "week";
export interface State {
  q: string;
  sort: Sort;
  /** extra queries overlaid on the chart (each the full query language) */
  cmp: string[];
  mode: "share" | "count";
  gran: Gran;
  /** selected post number (detail panel) */
  post: string;
}
export function readUrl(search = location.search): State {
  const p = new URLSearchParams(search);
  const sort = p.get("sort") as Sort;
  const gran = p.get("gran") as Gran;
  return {
    q: p.get("q") ?? "", sort: SORTS.includes(sort) ? sort : "newest", cmp: p.getAll("cmp").filter(Boolean).slice(0, 5),
    mode: p.get("y") === "count" ? "count" : "share", gran: gran === "month" || gran === "week" ? gran : "auto", post: p.get("post") ?? "",
  };
}
export function toUrl(s: State): string {
  const p = new URLSearchParams();
  if (s.q) p.set("q", s.q);
  if (s.sort !== "newest") p.set("sort", s.sort);
  for (const c of s.cmp) p.append("cmp", c);
  if (s.mode === "count") p.set("y", "count");
  if (s.gran !== "auto") p.set("gran", s.gran);
  if (s.post) p.set("post", s.post);
  const q = p.toString();
  return location.pathname + (q ? "?" + q : "");
}
