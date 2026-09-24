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
    summary: cleanText(raw.summary, 280) || undefined,
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

/**
 * Stable identity for session context used to skip duplicate Nova Context
 * strips on consecutive agent_start events. Compares cwd / user / hostname /
 * shell only — recent_activity churn must not re-open a full context block.
 */
export function novaContextFingerprint(context?: NovaContextPayload | null): string {
  if (!context) return "";
  const s = context.session;
  const sessionPart = s
    ? [s.cwd ?? "", s.user ?? "", s.hostname ?? "", s.shell ?? ""].join("\0")
    : "";
  const hasSession = sessionPart.replace(/\0/g, "").length > 0;
  if (hasSession) return sessionPart;
  if (context.recent_activity?.length) return "activity-only";
  return "";
}

export function hasNovaContextContent(context?: NovaContextPayload | null): boolean {
  if (!context) return false;
  return Boolean(context.session || (context.recent_activity?.length ?? 0) > 0);
}
