import type { NovaContextPayload, NovaRecentActivityItem, NovaSessionContextView } from "./ai-types";

function cleanText(value: unknown, limit: number) {
  const text = String(value || "").replace(/\r/g, " ").replace(/\n/g, " ").trim();
  return text ? text.slice(0, limit) : "";
}

function normalizeStringList(value: unknown, limit: number) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => cleanText(item, limit))
    .filter(Boolean)
    .slice(0, 8);
}

function parseSession(value: unknown): NovaSessionContextView | undefined {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const session: NovaSessionContextView = {
    cwd: cleanText(raw.cwd, 240) || undefined,
    user: cleanText(raw.user, 80) || undefined,
    hostname: cleanText(raw.hostname, 120) || undefined,
    shell: cleanText(raw.shell, 160) || undefined,
    venv: cleanText(raw.venv, 160) || undefined,
    python: cleanText(raw.python, 180) || undefined,
    env_summary: normalizeStringList(raw.env_summary, 120),
    source: cleanText(raw.source, 80) || undefined,
    confidence: cleanText(raw.confidence, 40) || undefined,
  };
  if (!Object.values(session).some((value) => (Array.isArray(value) ? value.length > 0 : Boolean(value)))) {
    return undefined;
  }
  if (!session.env_summary?.length) {
    delete session.env_summary;
  }
  return session;
}

function parseRecentActivityItem(value: unknown): NovaRecentActivityItem | null {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const command = cleanText(raw.command, 180);
  if (!command) return null;
  const exitCodeRaw = raw.exit_code;
  const exitCode =
    typeof exitCodeRaw === "number"
      ? exitCodeRaw
      : typeof exitCodeRaw === "string" && exitCodeRaw.trim() !== "" && !Number.isNaN(Number(exitCodeRaw))
        ? Number(exitCodeRaw)
        : undefined;
  return {
    command,
    cwd: cleanText(raw.cwd, 240) || undefined,
    exit_code: exitCode,
    source: cleanText(raw.source, 40) || undefined,
  };
}

export function parseNovaContextPayload(value: unknown): NovaContextPayload {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const session = parseSession(raw.session);
  const recentActivity = Array.isArray(raw.recent_activity)
    ? raw.recent_activity
        .map((item) => parseRecentActivityItem(item))
        .filter((item): item is NovaRecentActivityItem => item !== null)
        .slice(0, 8)
    : [];

  const result: NovaContextPayload = {};
  if (session) {
    result.session = session;
  }
  if (recentActivity.length) {
    result.recent_activity = recentActivity;
  }
  return result;
}
