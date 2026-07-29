import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const ALLOWED_ADVISORY = "GHSA-qwww-vcr4-c8h2";
const ALLOWED_ROUTER_VERSION = "7.18.2";
const HIGH_SEVERITIES = new Set(["high", "critical"]);
const SOURCE_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const RSC_API_TOKENS = [
  "createCallServer",
  "decodeReply",
  "react-server-client",
  "routeRSCServerRequest",
  "RSCHydratedRouter",
  "RSCStaticRouter",
  "unstable_RSC",
];

function productionSources(root) {
  const sources = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(path);
      } else if (
        SOURCE_EXTENSIONS.has(extname(entry.name)) &&
        !entry.name.includes(".test.") &&
        !entry.name.includes(".spec.")
      ) {
        sources.push([relative(root, path), readFileSync(path, "utf8")]);
      }
    }
  };
  visit(join(root, "src"));
  return sources;
}

function advisoryIds(vulnerability) {
  return (vulnerability?.via ?? [])
    .filter((item) => item && typeof item === "object")
    .map((item) => String(item.url ?? item.title ?? ""))
    .filter(Boolean);
}

export function auditPolicyErrors(audit, lock, sources) {
  if (audit?.error) return [`npm audit failed: ${audit.error.summary ?? audit.error.code ?? "unknown error"}`];

  const highEntries = Object.entries(audit?.vulnerabilities ?? {}).filter(([, vulnerability]) =>
    HIGH_SEVERITIES.has(vulnerability?.severity),
  );
  if (highEntries.length === 0) return [];

  const names = highEntries.map(([name]) => name).sort();
  if (JSON.stringify(names) !== JSON.stringify(["react-router", "react-router-dom"])) {
    return [`unapproved high or critical npm vulnerabilities: ${names.join(", ")}`];
  }

  const router = audit.vulnerabilities["react-router"];
  const routerDom = audit.vulnerabilities["react-router-dom"];
  const advisories = advisoryIds(router);
  if (advisories.length !== 1 || !advisories[0].includes(ALLOWED_ADVISORY)) {
    return [`react-router high severity advisory is not the reviewed ${ALLOWED_ADVISORY} exception`];
  }
  if ((routerDom.via ?? []).some((item) => item !== "react-router")) {
    return ["react-router-dom includes a high severity advisory outside the reviewed react-router exception"];
  }

  const packages = lock?.packages ?? {};
  for (const name of ["react-router", "react-router-dom"]) {
    const version = packages[`node_modules/${name}`]?.version;
    if (version !== ALLOWED_ROUTER_VERSION) {
      return [`${name} ${version ?? "missing"} requires a new security review before an audit exception`];
    }
  }

  const rscUsage = [];
  for (const [path, source] of sources) {
    for (const token of RSC_API_TOKENS) {
      if (source.includes(token)) rscUsage.push(`${path}: ${token}`);
    }
  }
  if (rscUsage.length > 0) {
    return [`the React Router RSC-only advisory is applicable: ${rscUsage.join(", ")}`];
  }
  return [];
}

function main() {
  const command = process.platform === "win32" ? (process.env.ComSpec ?? "cmd.exe") : "npm";
  const args = process.platform === "win32" ? ["/d", "/s", "/c", "npm audit --json"] : ["audit", "--json"];
  const result = spawnSync(command, args, {
    cwd: FRONTEND_ROOT,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  let audit;
  try {
    audit = JSON.parse(result.stdout || "");
  } catch {
    console.error(result.stderr || result.error || "npm audit did not return valid JSON");
    return 1;
  }

  const lock = JSON.parse(readFileSync(join(FRONTEND_ROOT, "package-lock.json"), "utf8"));
  const errors = auditPolicyErrors(audit, lock, productionSources(FRONTEND_ROOT));
  if (errors.length > 0) {
    console.error("npm audit policy: FAIL");
    for (const error of errors) console.error(`- ${error}`);
    return 1;
  }

  const highCount = Object.values(audit.vulnerabilities ?? {}).filter((item) =>
    HIGH_SEVERITIES.has(item?.severity),
  ).length;
  if (highCount > 0) {
    console.log(
      `npm audit policy: PASS (${ALLOWED_ADVISORY} is RSC-only; WebTrerm has no production RSC API usage)`,
    );
  } else {
    console.log("npm audit policy: PASS (no high or critical vulnerabilities)");
  }
  return 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
