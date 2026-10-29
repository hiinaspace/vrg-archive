// Mirrors site/src/vrg_site/tok.py -- keep in sync. Adapted from worldsearch (WTFPL, hiinaspace/vrcwscrape).
const CJK = "\\u3005-\\u3007\\u3040-\\u30ff\\u31f0-\\u31ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\uac00-\\ud7af\\u{20000}-\\u{2fa1f}";
const WORD = "[\\p{L}\\p{N}\\p{M}]";
const TOK = new RegExp(`([${CJK}]+)|((?:(?![${CJK}])${WORD})+)`, "gu");
const STRIP = /⁠?>>\d+|\[\/?spoiler\]|https?:\/\/|www\./g;

export const CH_GREEN = "\u0001";
export const CH_NAME = "\u0002";
export const CH_TRIP = "\u0003";
export const CH_FILE = "\u0004";
const MAX_WORD = 32;

const CONFUSABLES: Record<string, string> = { "‚": ",", "․": "." };
const CONF_RE = /[‚․]/g;
export const norm = (s: string) => s.normalize("NFKC").toLowerCase().replace(CONF_RE, (c) => CONFUSABLES[c]);

/** plural folding for ASCII alphabetic words of 4+ letters (mirrors tok.stem) */
export function stem(w: string): string {
  if (w.length < 4 || !/^[a-z]+$/.test(w)) return w;
  if (w.endsWith("sses") || w.endsWith("xes")) return w.slice(0, -2);
  if (w.endsWith("s") && !w.endsWith("ss") && !w.endsWith("us") && !w.endsWith("is")) return w.slice(0, -1);
  return w;
}

export const clean = (t: string) => t.replace(STRIP, " ");

/** index tokens of a body / field (mirrors tok.tokens) */
export function tokens(text: string): string[] {
  const out: string[] = [];
  for (const m of norm(clean(text)).matchAll(TOK)) {
    if (m[1] !== undefined) {
      const cs = Array.from(m[1]);
      if (cs.length === 1) out.push(cs[0]);
      else for (let i = 0; i + 1 < cs.length; i++) out.push(cs[i] + cs[i + 1]);
    } else {
      out.push(stem(Array.from(m[2]).slice(0, MAX_WORD).join("")));
    }
  }
  return out;
}

/** tokens of `text` with the [start,end) offsets of the raw-text match each came from (for highlighting) */
export function tokensWithSpans(text: string): { t: string; s: number; e: number }[] {
  const out: { t: string; s: number; e: number }[] = [];
  const re = new RegExp(TOK.source, "gu");
  for (const m of text.matchAll(re)) {
    const s = m.index!;
    const raw = m[0];
    if (/^(?:https?|www)$/i.test(raw) && /^(?:https?:\/\/|www\.)/i.test(text.slice(s))) continue;
    const toks = tokens(raw);
    if (!toks.length) continue;
    if (m[1] !== undefined) {
      // CJK run: each bigram spans two characters
      const cs = Array.from(raw);
      let off = s;
      toks.forEach((t, i) => {
        const w = cs.length === 1 ? cs[0] : cs[i] + cs[i + 1];
        out.push({ t, s: off, e: off + w.length });
        off += cs[i].length;
      });
    } else out.push({ t: toks[0], s, e: s + raw.length });
  }
  return out;
}

export function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** greentext lines of a body, newline-joined (mirrors tok.greentext) */
export const greentext = (body: string) => body.split("\n").filter((l) => l.startsWith(">") && !l.startsWith(">>")).join("\n");
