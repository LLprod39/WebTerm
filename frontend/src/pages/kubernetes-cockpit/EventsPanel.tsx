import { Activity } from "lucide-react";

import type { KubernetesClusterEvent } from "@/api";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";

function eventTone(severity: string): "success" | "warning" | "danger" | "neutral" | "info" {
  const s = (severity || "").toLowerCase();
  if (s === "error") return "danger";
  if (s === "warning") return "warning";
  if (s === "info" || s === "normal") return "info";
  return "neutral";
}

function formatTime(value: string | null, lang: string): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function EventsPanel({
  lang,
  events,
  loading,
  namespace,
  embedded = false,
}: {
  lang: string;
  events: KubernetesClusterEvent[];
  loading: boolean;
  namespace: string;
  embedded?: boolean;
}) {
  return (
    <section data-ui-slot="cockpit-events" className="flex min-h-0 flex-1 flex-col">
      {embedded ? null : (
        <div className="border-b border-border px-6 py-5">
          <h3 className="text-lg font-semibold text-foreground">
            {localize(lang, "Events · namespace", "Events · namespace")}
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {namespace
              ? localize(
                  lang,
                  `События Kubernetes для «${namespace}»: Warning, рестарты, ошибки scheduling.`,
                  `Kubernetes events for “${namespace}”: Warning, restarts, scheduling errors.`,
                )
              : localize(lang, "Сначала выберите namespace", "Select a namespace first")}
          </p>
        </div>
      )}

      <div className="min-h-[16rem] flex-1 overflow-auto">
        {!namespace ? (
          <EmptyState
            className="m-0 border-0 bg-transparent py-14"
            icon={<Activity className="h-6 w-6" />}
            title={localize(lang, "Namespace не выбран", "No namespace selected")}
            description={localize(lang, "События появятся после выбора namespace.", "Events appear after you select a namespace.")}
          />
        ) : loading ? (
          <div className="px-6 py-10 text-base text-muted-foreground">
            {localize(lang, "Загрузка событий…", "Loading events…")}
          </div>
        ) : events.length === 0 ? (
          <EmptyState
            className="m-0 border-0 bg-transparent py-14"
            icon={<Activity className="h-6 w-6" />}
            title={localize(lang, "Событий нет", "No events")}
            description={localize(lang, "В этом namespace нет недавних событий.", "No recent events in this namespace.")}
          />
        ) : (
          <ul className="divide-y divide-border">
            {events.slice(0, 40).map((event) => (
              <li key={event.id} className="px-5 py-4 sm:px-6">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{formatTime(event.created_at, lang)}</span>
                  <StatusBadge label={event.severity || "info"} tone={eventTone(event.severity)} className="normal-case tracking-normal" />
                  <span className="text-sm font-semibold text-foreground">{event.reason || "—"}</span>
                </div>
                <p className="mt-2 text-base leading-7 text-foreground/90">{event.message}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {[event.involved_kind, event.involved_name].filter(Boolean).join("/") || event.namespace || "—"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
