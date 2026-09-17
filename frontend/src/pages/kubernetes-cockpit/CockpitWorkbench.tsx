import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import type { KubernetesClusterEvent, KubernetesPodLogsResponse, KubernetesPodRef } from "@/api";
import { Button } from "@/components/ui/button";
import { ContentPanel } from "@/components/system/ContentPanel";
import { StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { humanPodStatus } from "./cockpitCopy";
import { EventsPanel } from "./EventsPanel";
import { ExecStubPanel } from "./ExecStubPanel";
import { ExplainLogsPanel } from "./ExplainLogsPanel";
import { PodLogsPanel } from "./PodLogsPanel";
import { podPhaseTone, type ExplainLogsResult } from "./types";

type WorkbenchTab = "logs" | "events" | "exec";

export function CockpitWorkbench({
  lang,
  pod,
  events,
  eventsLoading,
  namespace,
  logs,
  logsLoading,
  logsError,
  explain,
  onBack,
  onRefreshLogs,
  onExplain,
}: {
  lang: string;
  pod: KubernetesPodRef;
  events: KubernetesClusterEvent[];
  eventsLoading: boolean;
  namespace: string;
  logs?: KubernetesPodLogsResponse;
  logsLoading: boolean;
  logsError: unknown;
  explain: ExplainLogsResult | null;
  onBack: () => void;
  onRefreshLogs: () => void;
  onExplain: () => void;
}) {
  const [tab, setTab] = useState<WorkbenchTab>("logs");

  const podEvents = events.filter((event) => {
    if (event.involved_name && event.involved_name === pod.name) return true;
    return (event.message || "").includes(pod.name);
  });

  const tabs: Array<{ id: WorkbenchTab; label: string }> = [
    { id: "logs", label: localize(lang, "Логи", "Logs") },
    { id: "events", label: localize(lang, "События", "Events") },
    { id: "exec", label: localize(lang, "Exec", "Exec") },
  ];

  return (
    <ContentPanel className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-4 py-4 sm:px-5">
        <div className="min-w-0 space-y-2">
          <Button type="button" variant="ghost" size="sm" className="h-8 -ml-2 gap-1.5 px-2" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" aria-hidden />
            {localize(lang, "К списку pods", "Back to pods")}
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-lg font-semibold tracking-tight text-foreground" title={pod.name}>
              {pod.name}
            </h2>
            <StatusBadge
              label={pod.phase || pod.health}
              tone={podPhaseTone(pod.phase, pod.health)}
              className="normal-case tracking-normal"
            />
          </div>
          <p className="text-sm text-muted-foreground">{humanPodStatus(pod, lang)}</p>
          <p className="font-mono text-xs text-muted-foreground">
            {pod.namespace}
            {pod.node_name ? ` · ${pod.node_name}` : ""}
            {` · ${pod.restart_count} ${localize(lang, "рестартов", "restarts")}`}
          </p>
        </div>
      </div>

      <div
        className="flex gap-5 border-b border-border px-4 sm:px-5"
        role="tablist"
        aria-label={localize(lang, "Разделы pod", "Pod sections")}
      >
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={cn(
              "h-10 border-b-2 px-1 text-sm transition-colors",
              tab === item.id
                ? "border-primary font-medium text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "logs" ? (
        <div role="tabpanel" className="space-y-0">
          <PodLogsPanel
            lang={lang}
            pod={pod}
            logs={logs}
            loading={logsLoading}
            error={logsError}
            explaining={false}
            onRefresh={onRefreshLogs}
            onExplain={onExplain}
          />
          <ExplainLogsPanel lang={lang} result={explain} />
        </div>
      ) : null}

      {tab === "events" ? (
        <div role="tabpanel">
          <EventsPanel
            lang={lang}
            events={podEvents.length ? podEvents : events}
            loading={eventsLoading}
            namespace={namespace}
            embedded
          />
        </div>
      ) : null}

      {tab === "exec" ? (
        <div role="tabpanel">
          <ExecStubPanel lang={lang} pod={pod} />
        </div>
      ) : null}
    </ContentPanel>
  );
}
