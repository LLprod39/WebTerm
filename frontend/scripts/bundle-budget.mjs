import { readFile, readdir, mkdir, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import path from "node:path";

const manifest = JSON.parse(await readFile("dist/.vite/manifest.json", "utf8"));
const entry = Object.values(manifest).find((item) => item.isEntry);
if (!entry) throw new Error("Build manifest has no application entry");
const initial = new Set();
function visit(item) {
  if (initial.has(item.file)) return;
  initial.add(item.file);
  for (const key of item.imports ?? []) visit(manifest[key]);
}
visit(entry);
const assets = [];
for (const name of await readdir("dist/assets")) {
  if (!/\.(js|css)$/.test(name)) continue;
  const bytes = await readFile(path.join("dist/assets", name));
  assets.push({
    file: `assets/${name}`,
    bytes: bytes.length,
    gzip: gzipSync(bytes).length,
    initial: initial.has(`assets/${name}`),
  });
}
const initialJsGzip = assets
  .filter((a) => a.initial && a.file.endsWith(".js"))
  .reduce((sum, a) => sum + a.gzip, 0);
const largestChunkGzip = Math.max(
  ...assets.filter((a) => a.file.endsWith(".js")).map((a) => a.gzip),
);
const cssGzip = assets
  .filter((a) => a.file.endsWith(".css"))
  .reduce((sum, a) => sum + a.gzip, 0);
const limits = {
  initialJsGzip: 250_000,
  largestChunkGzip: 300_000,
  cssGzip: 65_000,
};
const measurements = { initialJsGzip, largestChunkGzip, cssGzip };
const passed = Object.entries(measurements).every(
  ([key, value]) => value <= limits[key],
);
await mkdir("artifacts", { recursive: true });
await writeFile(
  "artifacts/bundle-budget.json",
  JSON.stringify({ passed, limits, measurements, assets }, null, 2),
);
console.log(JSON.stringify({ passed, limits, measurements }, null, 2));
if (!passed) process.exitCode = 1;
