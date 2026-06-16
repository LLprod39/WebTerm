import { localize } from "@/lib/i18n";

export function formatCommandOutput(output: unknown): string {
  if (typeof output === "string") return output;
  if (!output || typeof output !== "object") return "(no output)";

  const value = output as Record<string, unknown>;
  const stdout = typeof value.stdout === "string" ? value.stdout : "";
  const stderr = typeof value.stderr === "string" ? value.stderr : "";
  const exitCode = value.exit_code;

  if (stdout || stderr || exitCode !== undefined) {
    const parts: string[] = [];
    if (stdout) parts.push(`STDOUT:\n${stdout}`);
    if (stderr) parts.push(`STDERR:\n${stderr}`);
    if (exitCode !== undefined) parts.push(`EXIT CODE: ${String(exitCode)}`);
    return parts.join("\n\n");
  }

  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

export function formatServerCount(count: number, lang: string) {
  if (lang !== "ru") return `${count} ${count === 1 ? "server" : "servers"}`;
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} сервер`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} сервера`;
  return `${count} серверов`;
}

export function displayServerGroupName(groupName: string, lang: string) {
  const normalized = groupName.trim().toLowerCase();
  if (!normalized || normalized === "ungrouped" || normalized === "all servers") {
    return localize(lang, "Без группы", "Ungrouped");
  }
  if (normalized === "production") return localize(lang, "Продакшен", "Production");
  if (normalized === "staging") return localize(lang, "Тестовый стенд", "Staging");
  return groupName;
}
