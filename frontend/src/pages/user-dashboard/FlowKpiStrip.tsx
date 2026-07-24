import { Sparkline } from "@/components/dashboard/Sparkline";
import { StatStrip, StatStripItem } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

export function FlowKpiStrip({
  lang,
  onlineServers,
  totalServers,
  runs7d,
  runSpark,
  activeAlerts,
  tokensHint,
}: {
  lang: "ru" | "en";
  onlineServers: number | null;
  totalServers: number;
  runs7d: number;
  runSpark: number[];
  activeAlerts: number;
  tokensHint: string;
}) {
  const onlineLabel =
    onlineServers === null
      ? "—"
      : `${onlineServers}/${totalServers || "—"}`;

  return (
    <StatStrip>
      <StatStripItem
        label={localize(lang, "Серверы онлайн", "Servers online")}
        value={onlineLabel}
        hint={localize(lang, "healthy + warning", "healthy + warning")}
        tone={onlineServers !== null && totalServers > 0 && onlineServers < totalServers ? "warning" : "success"}
      />
      <div className="bg-card px-4 py-3 sm:px-5">
        <div className="text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground/70">
          {localize(lang, "Прогоны агентов", "Agent runs")}
        </div>
        <div className="mt-1 flex items-end justify-between gap-3">
          <div className="font-display text-xl font-bold tabular-nums tracking-tight leading-none text-foreground">
            {runs7d}
          </div>
          <div className="h-8 w-20 text-primary">
            <Sparkline data={runSpark.length >= 2 ? runSpark : [0, 0.5, 1, 0.7, 0.9]} height={32} width={80} strokeWidth={1.5} />
          </div>
        </div>
        <div className="mt-1 text-xs leading-4 text-muted-foreground/70">
          {localize(lang, "недавние в ленте", "recent in feed")}
        </div>
      </div>
      <StatStripItem
        label={localize(lang, "Активные алерты", "Active alerts")}
        value={activeAlerts}
        hint={activeAlerts ? localize(lang, "требуют внимания", "need attention") : localize(lang, "тихо", "all clear")}
        tone={activeAlerts ? "danger" : "success"}
      />
      <StatStripItem
        label={localize(lang, "Токены ИИ", "AI tokens")}
        value="—"
        hint={tokensHint}
        tone="default"
      />
    </StatStrip>
  );
}
