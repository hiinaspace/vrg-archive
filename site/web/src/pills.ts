// Query pills (adapted from worldsearch, WTFPL): each top-level condition is removable and its sign flips include/exclude.
import { flipPill, parseQuery, removePill } from "./query";
import { esc } from "./util";

export function createPills(host: HTMLElement, getQ: () => string, setQ: (q: string) => void) {
  let pillsNow: ReturnType<typeof parseQuery>["pills"] = [];
  function render() {
    const parse = parseQuery(getQ());
    pillsNow = parse.pills;
    host.hidden = pillsNow.length === 0 && parse.errors.length === 0;
    host.innerHTML = pillsNow.map((p, i) => `<span class="pill ${p.negated ? "exc" : "inc"}" data-i="${i}">`
      + `<button type="button" class="sign" title="click to ${p.negated ? "include" : "exclude"} instead" aria-label="${p.negated ? "excluded" : "included"}; flip">${p.negated ? "−" : "+"}</button>`
      + `<span class="plabel">${esc(p.label)}</span><button type="button" class="x" aria-label="remove ${esc(p.label)}">×</button></span>`).join("")
      + (parse.errors.length ? `<span class="perr" role="note">${esc(parse.errors[0])}</span>` : "");
  }
  host.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    const el = t.closest(".pill") as HTMLElement | null;
    const p = el ? pillsNow[+el.dataset.i!] : null;
    if (!p) return;
    const q = getQ();
    if (t.closest(".x")) setQ(removePill(q, p));
    else if (t.closest(".sign")) setQ(flipPill(q, p));
  });
  return { render };
}

const EXAMPLES: [string, string][] = [
  ["quest pro", "all words, any case; digits count; plurals fold"],
  ['"valve deckard"', "exact phrase"],
  ["slop -ai", "a leading - excludes"],
  ["(llm | gpt) -slop", "| or OR = either; parentheses group"],
  ["thread:1978", "one thread (edition number)"],
  ["after:2023-05 before:2024", "date range (also date:2023, date:2023-01..2023-06)"],
  ["has:image ext:webm", "image posts; file type jpg png gif webm mp4"],
  ["op:yes", "first posts of threads"],
  ["replies:>=5", "posts with at least 5 replies"],
  ["domain:youtube.com", "posts linking a site"],
  ["name:hiina", "poster name; trip:abc123 for tripcodes"],
  ["filename:vrchat", "words in the posted file name"],
  ["greentext:implying", "words only inside >greentext lines"],
  [">>585933859", "replies to that post"],
];
export function createSyntaxHelp(btn: HTMLElement, pop: HTMLElement, pick: (q: string) => void) {
  pop.innerHTML = `<h4>Search syntax</h4><p class="dim">Words are ANDed. Lowercase <code>and or not</code> are plain words. Click an example to add it.</p><table>`
    + EXAMPLES.map(([q, d]) => `<tr><td><button type="button" class="ex" data-q="${esc(q)}">${esc(q)}</button></td><td>${esc(d)}</td></tr>`).join("") + `</table>`;
  const toggle = (on?: boolean) => { const open = on ?? pop.hidden; pop.hidden = !open; btn.setAttribute("aria-expanded", String(open)); };
  btn.addEventListener("click", (e) => { e.stopPropagation(); toggle(); });
  pop.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest(".ex") as HTMLElement | null;
    if (b) { pick(b.dataset.q!); toggle(false); }
    e.stopPropagation();
  });
  document.addEventListener("click", () => toggle(false));
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });
}
