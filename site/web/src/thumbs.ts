// Thumbnails: JPEGs packed back to back in data/thumbs/pack<k>.bin, read with coalesced HTTP Range requests.
import type { Store } from "./data";

interface Want { pack: number; off: number; len: number; res: (u: string | null) => void }
const GAP = 8192, WAIT = 4;

export class Thumbs {
  private urls = new Map<string, Promise<string | null>>();
  private queue: Want[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private store: Store) {}

  url(th: number[]): Promise<string | null> {
    const key = th[0] + "," + th[1];
    let p = this.urls.get(key);
    if (!p) {
      p = new Promise((res) => {
        this.queue.push({ pack: th[0], off: th[1], len: th[2], res });
        this.timer ??= setTimeout(() => this.flush(), WAIT);
      });
      this.urls.set(key, p);
    }
    return p;
  }
  private flush() {
    this.timer = null;
    const q = this.queue.splice(0).sort((a, b) => a.pack - b.pack || a.off - b.off);
    const runs: Want[][] = [];
    for (const w of q) {
      const run = runs[runs.length - 1];
      const last = run?.[run.length - 1];
      if (run && last.pack === w.pack && w.off - (last.off + last.len) <= GAP) run.push(w); else runs.push([w]);
    }
    for (const run of runs) {
      const a = run[0], end = Math.max(...run.map((w) => w.off + w.len));
      this.store.range(`thumbs/pack${a.pack}.bin`, a.off, end - a.off).then((buf) => {
        for (const w of run) w.res(URL.createObjectURL(new Blob([buf.slice(w.off - a.off, w.off - a.off + w.len)], { type: "image/jpeg" })));
      }).catch(() => run.forEach((w) => w.res(null)));
    }
  }
}
