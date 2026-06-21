import { ShieldCheck } from "lucide-react";

import type { AdminDashboardData } from "@/api";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { getWidgetStringProp } from "@/components/dashboard/widgetProps";
import { SectionCard } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 shadow-sm bg-card/65",
  success: "border-emerald-500/25 bg-emerald-950/5 dark:bg-emerald-950/10 shadow-emerald-500/5",
  warning: "border-amber-500/25 bg-amber-950/5 dark:bg-amber-950/10 shadow-amber-500/5",
  danger: "border-red-500/25 bg-red-950/5 dark:bg-red-950/10 shadow-red-500/5",
};

function providerLabel(provider: string) {
  const key = provider.toLowerCase();
  if (key === "openai") return "OpenAI";
  if (key === "xai" || key === "grok") return key === "xai" ? "xAI" : "Grok";
  if (key === "gemini") return "Gemini";
  if (key === "claude") return "Claude";
  if (key === "ollama") return "Ollama";
  return provider;
}

function emptyValueLabel(lang: string) {
  return localize(lang, "нет данных", "n/a");
}

export function buildAdminUsageWidgets(d: AdminDashboardData, lang: string): WidgetDefinition[] {
  return [
    {
      id: "ai_cost_tokens",
      title: "Расходы и использование моделей",
      icon: <ShieldCheck className="h-4 w-4" />,
      defaultSize: { w: 8, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Запросы и провайдеры");
        const usageEntries = Object.entries(d.api_usage || {});

        return (
          <SectionCard title={title} icon={<ShieldCheck className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-2 md:hidden">
              {usageEntries.map(([provider, usage]) => {
                const errRate = usage.calls > 0 ? ((usage.errors / usage.calls) * 100).toFixed(1) : "0.0";
                return (
                  <div key={provider} className="rounded-xl border border-border/70 bg-secondary/5 p-3 text-xs">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-bold text-foreground/90">{providerLabel(provider)}</span>
                      <span className="font-mono text-xs text-muted-foreground">{usage.calls.toLocaleString()} выз.</span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <div className="text-muted-foreground">Вход</div>
                        <div className="font-mono text-foreground">{usage.input_tokens.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Выход</div>
                        <div className="font-mono text-foreground">{usage.output_tokens.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Ошибки</div>
                        <div className={cn("font-mono", usage.errors > 0 ? "text-red-500" : "text-foreground")}>{usage.errors} ({errRate}%)</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Стоимость</div>
                        <div className="font-mono text-emerald-500">${usage.cost_usd.toFixed(4)}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
              {usageEntries.length === 0 && (
                <div className="py-6 text-center text-xs text-muted-foreground">Нет зарегистрированных данных по API</div>
              )}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-border/60 text-muted-foreground text-xs uppercase font-bold tracking-wider">
                    <th className="py-2.5">Провайдер</th>
                    <th className="py-2.5 text-right font-semibold">Вызовы</th>
                    <th className="py-2.5 text-right font-semibold">Входные токен</th>
                    <th className="py-2.5 text-right font-semibold">Выходные токен</th>
                    <th className="py-2.5 text-right font-semibold">Ошибки</th>
                    <th className="py-2.5 text-right font-bold text-primary">Стоимость (USD)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {usageEntries.map(([provider, usage]) => {
                    const errRate = usage.calls > 0 ? ((usage.errors / usage.calls) * 100).toFixed(1) : "0.0";
                    return (
                      <tr key={provider} className="hover:bg-secondary/10 transition-colors">
                        <td className="py-3 font-bold text-foreground/90">{providerLabel(provider)}</td>
                        <td className="py-3 text-right font-mono">{usage.calls.toLocaleString()}</td>
                        <td className="py-3 text-right font-mono text-muted-foreground/80">{usage.input_tokens.toLocaleString()}</td>
                        <td className="py-3 text-right font-mono text-muted-foreground/80">{usage.output_tokens.toLocaleString()}</td>
                        <td className="py-3 text-right font-mono">
                          <span className={cn(usage.errors > 0 ? "text-red-500 font-bold" : "text-muted-foreground/80")}>
                            {usage.errors} ({errRate}%)
                          </span>
                        </td>
                        <td className="py-3 text-right font-bold font-mono text-emerald-500">${usage.cost_usd.toFixed(4)}</td>
                      </tr>
                    );
                  })}
                  {usageEntries.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-muted-foreground">Нет зарегистрированных данных по API</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </SectionCard>
        );
      },
    },
    {
      id: "active_providers",
      title: "Модели и статус",
      icon: <ShieldCheck className="h-4 w-4" />,
      defaultSize: { w: 4, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Модели и провайдеры");
        const providerEntries = Object.entries(d.providers || {});

        return (
          <SectionCard title={title} icon={<ShieldCheck className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-3">
              {providerEntries.map(([provider, info]) => (
                <div key={provider} className="flex items-center justify-between p-2.5 rounded-xl border border-border/80 bg-secondary/5 text-xs hover:border-primary/30 transition-all">
                  <div className="flex items-center gap-2">
                    <div className={cn("h-2 w-2 rounded-full shrink-0", info.enabled ? "bg-emerald-500" : "bg-muted-foreground/30")} />
                    <span className="font-semibold text-foreground/95">{providerLabel(provider)}</span>
                  </div>
                  <span className="text-xs font-mono text-muted-foreground bg-card border rounded-md px-2 py-0.5 max-w-[150px] truncate shadow-sm">
                    {info.model || emptyValueLabel(lang)}
                  </span>
                </div>
              ))}
              {providerEntries.length === 0 && (
                <div className="py-4 text-center text-xs text-muted-foreground">Провайдеры отсутствуют</div>
              )}
            </div>
          </SectionCard>
        );
      },
    },
  ];
}
