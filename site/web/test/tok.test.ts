import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fnv1a, greentext, stem, tokens } from "../src/tok";

const V = JSON.parse(readFileSync(resolve(process.cwd(), "../tests/tok_vectors.json"), "utf8").toString());
test("tokenizer matches the python vectors", () => {
  for (const [s, want] of V.tokens) assert.deepEqual(tokens(s), want, s);
  for (const [w, want] of V.stem) assert.equal(stem(w), want, w);
  for (const [s, want] of V.fnv) assert.equal(fnv1a(s), want, s);
  assert.equal(greentext(V.green[0]), V.green[1]);
});
