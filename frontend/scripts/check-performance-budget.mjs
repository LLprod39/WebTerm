import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const artifactRoot = path.join(frontendRoot, "artifacts");
const targetUrl = "http://127.0.0.1:4174/login";
const runs = 3;
const budgets = {
  categories: {
    performance: { minimum: 0.75 },
    accessibility: { minimum: 0.95 },
    "best-practices": { minimum: 0.9 },
    seo: { minimum: 0.9 },
  },
  audits: {
    "first-contentful-paint": { maximumMs: 2500 },
    "largest-contentful-paint": { maximumMs: 3500 },
    "speed-index": { maximumMs: 3500 },
    "total-blocking-time": { maximumMs: 300 },
    "cumulative-layout-shift": { maximum: 0.1 },
  },
};

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: frontendRoot, stdio: "inherit", ...options });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${path.basename(command)} exited with ${code ?? signal}`));
    });
  });
}

async function waitForServer(url) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The preview server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Preview server did not become ready at ${url}`);
}

await mkdir(artifactRoot, { recursive: true });

const viteEntry = path.join(frontendRoot, "node_modules", "vite", "bin", "vite.js");
const lighthouseEntry = path.join(frontendRoot, "node_modules", "lighthouse", "cli", "index.js");
const preview = spawn(
  process.execPath,
  [viteEntry, "preview", "--host", "127.0.0.1", "--port", "4174", "--strictPort"],
  { cwd: frontendRoot, stdio: "inherit" },
);

let chromePath = process.env.CHROME_PATH;
if (!chromePath) {
  try {
    const { chromium } = await import("playwright");
    chromePath = chromium.executablePath();
  } catch {
    // Lighthouse will fall back to a system Chrome installation.
  }
}
const lighthouseEnvironment = chromePath
  ? { ...process.env, CHROME_PATH: chromePath }
  : process.env;

const reports = [];
try {
  await waitForServer(targetUrl);
  for (let index = 1; index <= runs; index += 1) {
    const reportPath = path.join(artifactRoot, `lighthouse-login-run-${index}.json`);
    try {
      await run(process.execPath, [
        lighthouseEntry,
        targetUrl,
        "--preset=desktop",
        "--only-categories=performance,accessibility,best-practices,seo",
        "--output=json",
        `--output-path=${reportPath}`,
        "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage",
        "--max-wait-for-load=30000",
        "--quiet",
      ], { env: lighthouseEnvironment });
    } catch (error) {
      // chrome-launcher can fail to remove its locked Windows temp profile after
      // a complete audit. A valid LHR is authoritative; malformed/missing output
      // still fails below.
      console.warn(`Lighthouse process warning: ${error.message}`);
    }
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    if (!report.categories?.performance || !report.audits?.["largest-contentful-paint"]) {
      throw new Error(`Incomplete Lighthouse report: ${reportPath}`);
    }
    reports.push(report);
  }
} finally {
  preview.kill();
}

const categoryMedians = Object.fromEntries(
  Object.keys(budgets.categories).map((id) => [
    id,
    median(reports.map((report) => report.categories[id].score)),
  ]),
);
const auditMedians = Object.fromEntries(
  Object.keys(budgets.audits).map((id) => [
    id,
    median(reports.map((report) => report.audits[id].numericValue)),
  ]),
);

const violations = [];
for (const [id, budget] of Object.entries(budgets.categories)) {
  const actual = categoryMedians[id];
  if (actual < budget.minimum) violations.push(`${id} score ${actual} < ${budget.minimum}`);
}
for (const [id, budget] of Object.entries(budgets.audits)) {
  const actual = auditMedians[id];
  const maximum = budget.maximumMs ?? budget.maximum;
  if (actual > maximum) violations.push(`${id} ${actual} > ${maximum}`);
}

const summary = {
  state: violations.length === 0 ? "passed" : "failed",
  targetUrl,
  runs,
  budgets,
  medians: { categories: categoryMedians, audits: auditMedians },
  lighthouseVersion: reports[0].lighthouseVersion,
  fetchTime: reports[0].fetchTime,
  violations,
};
await writeFile(
  path.join(artifactRoot, "lighthouse-budget.json"),
  `${JSON.stringify(summary, null, 2)}\n`,
);

console.log(`Lighthouse medians (${runs} runs): ${JSON.stringify(summary.medians)}`);
if (violations.length) {
  for (const violation of violations) console.error(`Lighthouse budget violation: ${violation}`);
  process.exitCode = 1;
} else {
  console.log("Lighthouse budget: PASS");
}
