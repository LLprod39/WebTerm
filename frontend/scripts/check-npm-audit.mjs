import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

export function assessAudit(report) {
  const counts = report?.metadata?.vulnerabilities;
  if (
    !counts ||
    !Number.isFinite(counts.high) ||
    !Number.isFinite(counts.critical)
  )
    throw new Error("Incomplete npm audit result");
  return {
    passed: counts.high === 0 && counts.critical === 0,
    high: counts.high,
    critical: counts.critical,
  };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const result = spawnSync(
    process.platform === "win32" ? "npm.cmd" : "npm",
    ["audit", "--json"],
    {
      encoding: "utf8",
      shell: process.platform === "win32",
      maxBuffer: 8 * 1024 * 1024,
    },
  );
  if (result.error) throw result.error;
  const assessment = assessAudit(JSON.parse(result.stdout));
  console.log(JSON.stringify(assessment));
  if (!assessment.passed) process.exitCode = 1;
}
