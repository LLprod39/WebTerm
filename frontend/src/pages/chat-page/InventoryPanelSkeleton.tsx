import { Loader2 } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type InventorySkeletonKind = "servers" | "agents" | "alerts" | "forecasts" | "list";

type Props = {
  kind?: InventorySkeletonKind;
  /** How many shimmer rows */
  rows?: number;
  className?: string;
  label?: string;
};

const LABELS: Record<InventorySkeletonKind, { ru: string; en: string }> = {
  servers: { ru: "Серверы", en: "Servers" },
  agents: { ru: "Агенты", en: "Agents" },
  alerts: { ru: "Алерты", en: "Alerts" },
  forecasts: { ru: "Прогнозы", en: "Forecasts" },
  list: { ru: "Список", en: "List" },
};

/**
 * Soft loading shell that matches Interactive* panels —
 * so stream → final inventory doesn't jump visually.
 */
export function InventoryPanelSkeleton({ kind = "list", rows = 5, className, label }: Props) {
  const { lang } = useI18n();
  const title = label || localize(lang, LABELS[kind].ru, LABELS[kind].en);
  const count = Math.max(3, Math.min(rows, 8));

  return (
    <div
      className={cn(
        "max-w-[min(520px,100%)] overflow-hidden rounded-sm border border-border/40 bg-card/30",
        className,
      )}
      role="status"
      aria-live="polite"
      aria-label={title}
    >
      <div className="flex items-center justify-between gap-3 px-3.5 pt-2.5 pb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium tracking-wide text-muted-foreground">{title}</span>
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/60 motion-reduce:animate-none" />
        </div>
        <span className="text-[11px] text-muted-foreground/50">
          {localize(lang, "загрузка", "loading")}
        </span>
      </div>

      <ul className="pb-2">
        {Array.from({ length: count }).map((_, i) => (
          <li key={i} className="flex items-center gap-2.5 px-3.5 py-1.5">
            <span className="h-1 w-1 shrink-0 rounded-full bg-muted-foreground/20" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div
                className="h-2.5 rounded-full bg-foreground/[0.06]"
                style={{
                  width: `${58 + ((i * 17) % 28)}%`,
                  animation: "inventory-shimmer 1.4s ease-in-out infinite",
                  animationDelay: `${i * 90}ms`,
                }}
              />
              <div
                className="h-1.5 rounded-full bg-foreground/[0.04]"
                style={{
                  width: `${32 + ((i * 13) % 22)}%`,
                  animation: "inventory-shimmer 1.4s ease-in-out infinite",
                  animationDelay: `${i * 90 + 120}ms`,
                }}
              />
            </div>
            <div
              className="h-5 w-5 shrink-0 rounded-full bg-foreground/[0.04]"
              style={{
                animation: "inventory-shimmer 1.4s ease-in-out infinite",
                animationDelay: `${i * 90 + 60}ms`,
              }}
            />
          </li>
        ))}
      </ul>

      <style>{`
        @keyframes inventory-shimmer {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

/** Infer which inventory skeleton to show from tool name / stream text. */
export function inferInventorySkeletonKind(
  toolNames: string[],
  streamText = "",
): InventorySkeletonKind | null {
  const joined = toolNames.join(" ").toLowerCase();
  const text = streamText.toLowerCase();

  const looksForecasts =
    /\bforecasts?\b/.test(joined) ||
    /server_forecasts|operator\.server_forecasts|prediction/.test(joined) ||
    (/\beta\b/.test(text) && (/\bdisk\b/.test(text) || /\bcert\b/.test(text) || /\bпрогноз/.test(text)));

  const looksAgents =
    /\bagents?\b/.test(joined) ||
    /agents?\.list|list_agents|agents_list/.test(joined) ||
    (/\bmode\b/.test(text) && /\b(mini|full|multi)\b/.test(text));

  const looksAlerts =
    /\balerts?\b/.test(joined) ||
    /alert/.test(joined) ||
    (/\bseverity\b/.test(text) && /\balert\b/.test(text));

  // Only full inventory list — NOT resolve_server / server_info / server_metrics (no card in chat).
  const looksServers =
    !/resolve_server|server_info|server_metrics|run_command|run_fanout/.test(joined) &&
    (/list_servers|servers?\.list|operator\.list_servers|fleet_status|inventory/.test(joined) ||
      (/\bhost\b/.test(text) && (/\bport\b/.test(text) || /\btags?\b/.test(text))));

  // Prefer specific kinds
  if (looksForecasts) return "forecasts";
  if (looksAgents && !looksServers) return "agents";
  if (looksAlerts && !looksServers) return "alerts";
  if (looksServers) return "servers";
  if (looksAgents) return "agents";
  if (looksAlerts) return "alerts";

  // Markdown table forming in stream?
  if (hasMarkdownTable(streamText)) return "list";
  return null;
}

export function hasMarkdownTable(raw: string): boolean {
  const lines = String(raw || "").split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    const a = lines[i].trim();
    const b = lines[i + 1].trim();
    if (!a.includes("|")) continue;
    // header + separator or consecutive pipe rows
    if (/^\|?[\s\-:|]+\|?$/.test(b) || (b.includes("|") && a.split("|").length >= 3)) {
      return true;
    }
  }
  return false;
}
