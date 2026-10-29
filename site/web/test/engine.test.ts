import { test } from "node:test";
import { existsSync } from "node:fs";
import assert from "node:assert/strict";
import { Engine } from "../src/engine";
import { FileStore } from "./filestore";

const DIR = (process.env.VRG_DATA ?? "../../vrg-archive-data") + "/site-r1/dev-dist/data";
test("engine boots and answers", { skip: !existsSync(DIR + "/manifest.json") }, async () => {
  const e = await Engine.load(new FileStore(DIR));
  const r = await e.run("vrchat");
  console.log("vrchat", r.total, e.N);
  assert.ok(r.total > 0);
  const r2 = await e.run('"quest pro"');
  console.log("phrase", r2.total, r2.pending);
  const r3 = await e.run("vrchat -quest has:image");
  console.log("combo", r3.total);
  const p = await e.page(r, "newest", 0, 5);
  const rows = await e.rows(p.docs);
  console.log(rows.map((x) => x.no + " " + x.body.slice(0, 40)));
});
