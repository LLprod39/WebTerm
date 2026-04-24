import { useMemo } from "react";
import type { AiCommand } from "@/components/terminal/ai-types";

/**
 * Risk summary derived from backend F2-5 / F2-8 signals.
 *
 * Backend contract:
 *   - {@link AiCommand.risk_categories}: machine-readable categories like
 *     `"destructive_fs"`, `"system_control"` — used for grouping in the UI.
 *   - {@link AiCommand.risk_reasons}: human-readable one-liners per matched
 *     pattern (e.g. `"рекурсивное удаление с force (rm -rf)"`) — shown
 *     directly in a tooltip.
 *   - {@link AiCommand.reason}: canonical reason code driving the UI badge
 *     colour (forbidden / outside_allowlist / dangerous / ask_mode / "").
 *   - {@link AiCommand.exec_mode}: `"direct"` — safe stateless exec hint;
 *     `"pty"` — interactive shell (default).
 */
export type AiCommandRiskLevel = "safe" | "ask" | "dangerous" | "blocked";

export interface AiCommandRisk {
  /** High-level colour bucket for the risk badge. */
  level: AiCommandRiskLevel;
  /** Short label ("SAFE" / "ASK" / "DANGER" / "BLOCKED"). */
  label: string;
  /** Localized explanation for the tooltip. */
  tooltip: string;
  /** Unique category labels, suitable for chip rendering. */
  categories: string[];
  /** Raw reason sentences, one per matched pattern. */
  reasons: string[];
  /** ``true`` when the backend refused to let this command run. */
  isBlocked: boolean;
  /** Hybrid exec hint — informational for now (F2-8 v1). */
  execMode: "pty" | "direct";
}

const REASON_LABELS: Record<NonNullable<AiCommand["reason"]>, string> = {
  "": "",
  dangerous: "Опасная команда — требуется подтверждение",
  ask_mode: "Режим Ask — нужно подтвердить вручную",
  forbidden: "Команда запрещена политикой безопасности",
  outside_allowlist: "Команда вне разрешённого списка",
};

/**
 * Derive a UI-friendly risk snapshot from an AI command.
 *
 * The hook is pure/memoized: it returns a stable object for equal inputs so
 * consumers can safely use it as a dependency elsewhere.
 */
export function useAiCommandRisk(command: AiCommand): AiCommandRisk {
  return useMemo<AiCommandRisk>(() => {
    const categories = command.risk_categories?.filter(Boolean) ?? [];
    const reasons = command.risk_reasons?.filter(Boolean) ?? [];
    const isBlocked = Boolean(command.blocked);
    const reasonKey = command.reason ?? "";

    let level: AiCommandRiskLevel = "safe";
    let label = "SAFE";
    let tooltip = "Безопасная команда";

    if (isBlocked) {
      level = "blocked";
      label = "BLOCKED";
      tooltip = REASON_LABELS[reasonKey] || "Команда заблокирована";
    } else if (reasonKey === "dangerous") {
      level = "dangerous";
      label = "DANGER";
      tooltip = REASON_LABELS.dangerous;
    } else if (reasonKey === "ask_mode") {
      level = "ask";
      label = "ASK";
      tooltip = REASON_LABELS.ask_mode;
    }

    // Append per-match reasons to the tooltip when we have them.
    if (reasons.length > 0) {
      tooltip = `${tooltip}:\n${reasons.map((r) => `• ${r}`).join("\n")}`;
    }

    return {
      level,
      label,
      tooltip,
      categories,
      reasons,
      isBlocked,
      execMode: command.exec_mode === "direct" ? "direct" : "pty",
    };
  }, [command.risk_categories, command.risk_reasons, command.blocked, command.reason, command.exec_mode]);
}

const RISK_BADGE_CLASSES: Record<AiCommandRiskLevel, string> = {
  safe: "border-success/30 bg-success/10 text-success",
  ask: "border-primary/30 bg-primary/10 text-primary",
  dangerous: "border-warning/40 bg-warning/15 text-warning",
  blocked: "border-destructive/40 bg-destructive/15 text-destructive",
};

/** Tailwind class string for the risk badge — matches the existing palette. */
export function riskBadgeClass(level: AiCommandRiskLevel): string {
  return RISK_BADGE_CLASSES[level];
}
