import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = path.join(frontendRoot, "dist", "assets");
const artifactRoot = path.join(frontendRoot, "artifacts");
const budget = JSON.parse(await readFile(path.join(frontendRoot, "bundle-budget.json"), "utf8"));
const names = await readdir(assetsRoot);
const records = [];

for (const name of names.sort()) {
  const filePath = path.join(assetsRoot, name);
  const content = await readFile(filePath);
  records.push({
    name,
    bytes: content.byteLength,
    sha256: createHash("sha256").update(content).digest("hex"),
  });
}

const javascript = records.filter((record) => record.name.endsWith(".js"));
const css = records.filter((record) => record.name.endsWith(".css"));
const totalJavaScriptBytes = javascript.reduce((total, record) => total + record.bytes, 0);
const totalCssBytes = css.reduce((total, record) => total + record.bytes, 0);
const largestJavaScript = javascript.reduce(
  (largest, record) => (record.bytes > largest.bytes ? record : largest),
  { name: "none", bytes: 0, sha256: "" },
);
const violations = [];

if (totalJavaScriptBytes > budget.maxTotalJavaScriptBytes) {
  violations.push(`total JavaScript ${totalJavaScriptBytes} > ${budget.maxTotalJavaScriptBytes}`);
}
if (largestJavaScript.bytes > budget.maxLargestJavaScriptBytes) {
  violations.push(
    `largest JavaScript ${largestJavaScript.name} (${largestJavaScript.bytes}) > ${budget.maxLargestJavaScriptBytes}`,
  );
}
if (totalCssBytes > budget.maxTotalCssBytes) {
  violations.push(`total CSS ${totalCssBytes} > ${budget.maxTotalCssBytes}`);
}

const report = {
  state: violations.length === 0 ? "passed" : "failed",
  baselineCommit: budget.baselineCommit,
  totals: { totalJavaScriptBytes, totalCssBytes, largestJavaScript },
  limits: {
    maxTotalJavaScriptBytes: budget.maxTotalJavaScriptBytes,
    maxLargestJavaScriptBytes: budget.maxLargestJavaScriptBytes,
    maxTotalCssBytes: budget.maxTotalCssBytes,
  },
  violations,
  files: records,
};

await mkdir(artifactRoot, { recursive: true });
await writeFile(path.join(artifactRoot, "bundle-budget.json"), `${JSON.stringify(report, null, 2)}\n`);

console.log(`JavaScript total: ${totalJavaScriptBytes} bytes`);
console.log(`Largest JavaScript: ${largestJavaScript.name} (${largestJavaScript.bytes} bytes)`);
console.log(`CSS total: ${totalCssBytes} bytes`);
if (violations.length) {
  for (const violation of violations) console.error(`Bundle budget violation: ${violation}`);
  process.exitCode = 1;
} else {
  console.log("Bundle budget: PASS");
}
