import type { AiAssistantSettings, AiAutoReportMode, AiPreferences } from "./ai-types";

export const AI_PREFERENCES_STORAGE_KEY = "terminal_ai_preferences_v1";

export const DEFAULT_AI_SETTINGS: AiAssistantSettings = {
  memoryEnabled: true,
  memoryTtlRequests: 6,
  autoReport: "auto",
  confirmDangerousCommands: true,
  whitelistPatterns: [],
  blacklistPatterns: [],
  showSuggestedCommands: true,
  showExecutedCommands: true,
  dryRun: false,
  extraTargetServerIds: [],
  novaSessionContextEnabled: true,
  novaRecentActivityEnabled: true,
};

export const DEFAULT_AI_PREFERENCES: AiPreferences = {
  chatMode: "agent",
  executionMode: "auto",
  settings: DEFAULT_AI_SETTINGS,
};

function clampTtl(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_AI_SETTINGS.memoryTtlRequests;
  return Math.max(1, Math.min(20, Math.round(parsed)));
}

function normalizePatternList(value: unknown) {
  const source = Array.isArray(value) ? value : [];
  const seen = new Set<string>();
  const normalized: string[] = [];

  for (const item of source) {
    const line = String(item || "").trim();
    if (!line) continue;
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(line);
  }

  return normalized.slice(0, 50);
}

export function cloneAiSettings(settings: AiAssistantSettings): AiAssistantSettings {
  return {
    ...settings,
    whitelistPatterns: [...settings.whitelistPatterns],
    blacklistPatterns: [...settings.blacklistPatterns],
    extraTargetServerIds: [...settings.extraTargetServerIds],
  };
}

export function cloneAiPreferences(preferences: AiPreferences): AiPreferences {
  return {
    chatMode: preferences.chatMode,
    executionMode: preferences.executionMode,
    settings: cloneAiSettings(preferences.settings),
  };
}

export function sanitizeAiSettings(value: unknown): AiAssistantSettings {
  const raw = value && typeof value === "object" ? (value as Partial<AiAssistantSettings>) : {};
  const autoReport = raw.autoReport;
  const normalizedAutoReport: AiAutoReportMode =
    autoReport === "on" || autoReport === "off" || autoReport === "auto" ? autoReport : DEFAULT_AI_SETTINGS.autoReport;

  return {
    memoryEnabled: typeof raw.memoryEnabled === "boolean" ? raw.memoryEnabled : DEFAULT_AI_SETTINGS.memoryEnabled,
    memoryTtlRequests: clampTtl(raw.memoryTtlRequests),
    autoReport: normalizedAutoReport,
    confirmDangerousCommands:
      typeof raw.confirmDangerousCommands === "boolean"
        ? raw.confirmDangerousCommands
        : DEFAULT_AI_SETTINGS.confirmDangerousCommands,
    whitelistPatterns: normalizePatternList(raw.whitelistPatterns),
    blacklistPatterns: normalizePatternList(raw.blacklistPatterns),
    showSuggestedCommands:
      typeof raw.showSuggestedCommands === "boolean"
        ? raw.showSuggestedCommands
        : DEFAULT_AI_SETTINGS.showSuggestedCommands,
    showExecutedCommands:
      typeof raw.showExecutedCommands === "boolean"
        ? raw.showExecutedCommands
        : DEFAULT_AI_SETTINGS.showExecutedCommands,
    dryRun: typeof raw.dryRun === "boolean" ? raw.dryRun : DEFAULT_AI_SETTINGS.dryRun,
    extraTargetServerIds: Array.isArray(raw.extraTargetServerIds)
      ? Array.from(
          new Set(
            raw.extraTargetServerIds
              .map((value) => Number(value))
              .filter((value) => Number.isFinite(value) && value > 0),
          ),
        ).slice(0, 10)
      : DEFAULT_AI_SETTINGS.extraTargetServerIds,
    novaSessionContextEnabled:
      typeof raw.novaSessionContextEnabled === "boolean"
        ? raw.novaSessionContextEnabled
        : DEFAULT_AI_SETTINGS.novaSessionContextEnabled,
    novaRecentActivityEnabled:
      typeof raw.novaRecentActivityEnabled === "boolean"
        ? raw.novaRecentActivityEnabled
        : DEFAULT_AI_SETTINGS.novaRecentActivityEnabled,
  };
}

export function sanitizeAiPreferences(value: unknown): AiPreferences {
  const raw = value && typeof value === "object" ? (value as Partial<AiPreferences>) : {};
  const chatMode = raw.chatMode === "ask" || raw.chatMode === "agent" ? raw.chatMode : DEFAULT_AI_PREFERENCES.chatMode;
  const executionMode =
    raw.executionMode === "auto" ||
    raw.executionMode === "fast" ||
    raw.executionMode === "step" ||
    raw.executionMode === "agent"
      ? raw.executionMode
      : DEFAULT_AI_PREFERENCES.executionMode;

  return {
    chatMode,
    executionMode,
    settings: sanitizeAiSettings(raw.settings),
  };
}

export function readStoredAiPreferences(): AiPreferences {
  try {
    const stored = localStorage.getItem(AI_PREFERENCES_STORAGE_KEY);
    if (stored) {
      return sanitizeAiPreferences(JSON.parse(stored));
    }

    const legacyMode = localStorage.getItem("ai_execution_mode");
    if (legacyMode === "auto" || legacyMode === "fast" || legacyMode === "step") {
      return {
        ...cloneAiPreferences(DEFAULT_AI_PREFERENCES),
        chatMode: "agent",
        executionMode: legacyMode,
      };
    }
  } catch {
    return cloneAiPreferences(DEFAULT_AI_PREFERENCES);
  }

  return cloneAiPreferences(DEFAULT_AI_PREFERENCES);
}

export function serializeAiSettings(settings?: AiAssistantSettings) {
  if (!settings) return undefined;
  return {
    memory_enabled: settings.memoryEnabled,
    memory_ttl_requests: settings.memoryTtlRequests,
    auto_report: settings.autoReport,
    confirm_dangerous_commands: settings.confirmDangerousCommands,
    allowlist_patterns: settings.whitelistPatterns,
    blocklist_patterns: settings.blacklistPatterns,
    dry_run: settings.dryRun,
    extra_target_server_ids: settings.extraTargetServerIds,
    nova_session_context_enabled: settings.novaSessionContextEnabled,
    nova_recent_activity_enabled: settings.novaRecentActivityEnabled,
  };
}
