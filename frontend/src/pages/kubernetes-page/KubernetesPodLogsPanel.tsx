import { ScrollText } from "lucide-react";

import type { KubernetesPodLogsResponse } from "@/api";
import { Button } from "@/components/ui/button";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { statusLabel, statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";
import { DeepLinkButtons, type OnOpenDeepLink } from "@/pages/kubernetes-page/kubernetesDeepLinks";

export function KubernetesPodLogsPanel({
  lang,
  logs,
  loading,
  error,
  onClose,
  onOpenLink,
}: {
  lang: string;
  logs?: KubernetesPodLogsResponse;
  loading: boolean;
  error: unknown;
  onClose: () => void;
  onOpenLink?: OnOpenDeepLink;
}) {
  return (
    <SectionCard
      title={localize(lang, "Логи пода", "Pod logs")}
      description={localize(
        lang,
        "Ограниченный снимок с записью в аудит. Выполнение команд и поток логов заблокированы.",
        "Bounded snapshot with audit metadata; exec and streaming stay blocked.",
      )}
      icon={<ScrollText className="h-4 w-4" />}
      actions={
        <Button variant="outline" size="sm" onClick={onClose}>
          {localize(lang, "Закрыть", "Close")}
        </Button>
      }
    >
      {loading ? (
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4 text-sm text-muted-foreground">
          {localize(lang, "Загружаю логи", "Loading logs")}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-4 text-sm text-destructive">
          {localize(lang, "Не удалось загрузить логи", "Failed to load logs")}
        </div>
      ) : logs ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <div className="space-y-3">
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  label={logs.available ? localize(lang, "снимок", "snapshot") : logs.source}
                  tone={logs.available ? "success" : logs.source === "provider_error" ? "danger" : "neutral"}
                />
                <StatusBadge label={logs.target.namespace || "namespace"} tone="neutral" />
                <StatusBadge label={statusLabel(lang, logs.target.health)} tone={statusTone(logs.target.health)} />
                <StatusBadge label={`${logs.policy.requested_tail_lines} ${localize(lang, "строк", "lines")}`} tone="info" />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-foreground">{logs.target.name}</h3>
              <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                <div>{localize(lang, "Кластер:", "Cluster:")} {logs.target.cluster_name}</div>
                <div>{localize(lang, "Нода:", "Node:")} {logs.target.node_name || localize(lang, "нет", "none")}</div>
                <div>{localize(lang, "Фаза:", "Phase:")} {logs.target.phase || localize(lang, "нет", "none")}</div>
                <div>{localize(lang, "Провайдер:", "Provider:")} {logs.provider?.name || localize(lang, "не настроен", "not configured")}</div>
              </div>
              {logs.message ? <div className="mt-3 text-xs text-muted-foreground">{logs.message}</div> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <DeepLinkButtons
                  links={logs.target.links}
                  lang={lang}
                  target={{
                    target_type: "pod",
                    target_id: logs.target.id,
                    target_name: logs.target.name,
                    cluster_id: logs.target.cluster_id,
                    provider: "rancher",
                  }}
                  onOpenLink={onOpenLink}
                  limit={4}
                />
              </div>
            </div>

            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{localize(lang, "Политика", "Policy")}</div>
              <div className="mt-2 text-sm text-foreground">
                {logs.policy.mutates_state ? localize(lang, "Изменения разрешены", "Changes allowed") : localize(lang, "Только просмотр", "Read-only")}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusBadge label={logs.policy.streaming ? localize(lang, "поток", "streaming") : localize(lang, "снимок", "snapshot")} tone={logs.policy.streaming ? "warning" : "success"} />
                {logs.policy.blocked_actions.slice(0, 8).map((action) => (
                  <StatusBadge key={action} label={action} tone="neutral" />
                ))}
              </div>
            </div>
          </div>

          <pre className="max-h-[28rem] overflow-auto rounded-lg border border-border/70 bg-secondary/25 p-4 text-xs leading-5 text-foreground">
            {logs.lines.length
              ? logs.lines.join("\n")
              : localize(
                lang,
                "Строки логов недоступны. Используйте проверенную ссылку на провайдера, если она есть.",
                "Log lines are not available. Use the audited provider link when present.",
              )}
          </pre>
        </div>
      ) : null}
    </SectionCard>
  );
}
