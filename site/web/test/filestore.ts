import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import type { Store } from "../src/data";

/** Store backed by a dist/data directory (for node tests and the smoke script). */
export class FileStore implements Store {
  stats = { bytes: 0, requests: 0 };
  constructor(public dir: string) {}
  async bin(path: string) {
    const p = this.dir + "/" + path;
    if (!existsSync(p)) throw new Error("missing " + path);
    const b = readFileSync(p);
    this.stats.bytes += b.length; this.stats.requests++;
    const u = b.length > 1 && b[0] === 0x1f && b[1] === 0x8b ? gunzipSync(b) : b;
    return new Uint8Array(u.buffer, u.byteOffset, u.byteLength);
  }
  async range(path: string, off: number, len: number) {
    const b = readFileSync(this.dir + "/" + path).subarray(off, off + len);
    this.stats.bytes += b.length; this.stats.requests++;
    return new Uint8Array(b);
  }
}
