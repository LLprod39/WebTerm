import { Boxes, ChevronRight } from "lucide-react";

import type { KubernetesPodRef } from "@/api";
import { ContentPanel } from "@/components/system/ContentPanel";
import { EmptyState, StatusBadge } from "@/components/ui/page-shell";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { humanPodStatus, needsAttention } from "./cockpitCopy";
import { isPodReady, podPhaseTone } from "./types";

export function PodListPanel({
  lang,
  pods,
  selectedPodId,
  loading,
  namespace,
  onSelect,
}: {
  lang: string;
  pods: KubernetesPodRef[];
  selectedPodId: string;
  loading: boolean;
  namespace: string;
  onSelect: (podId: string) => void;
}) {
  const attention = pods.filter((pod) => needsAttention(pod));
  const healthy = pods.filter((pod) => !needsAttention(pod));

  return (
    <ContentPanel className="overflow-hidden">
      {!namespace ? (
        <EmptyState
          className="m-0 border-0 bg-transparent py-16"
          icon={<Boxes className="h-6 w-6" />}
          title={localize(lang, "Выберите namespace", "Pick a namespace")}
          description={localize(
            lang,
            "Выберите namespace в фильтре сверху, чтобы загрузить поды.",
            "Select a namespace in the filter above to load pods.",
          )}
        />
      ) : loading ? (
        <div className="px-5 py-10 text-sm text-muted-foreground">
          {localize(lang, "Загрузка подов…", "Loading pods…")}
        </div>
      ) : pods.length === 0 ? (
        <EmptyState
          className="m-0 border-0 bg-transparent py-16"
          icon={<Boxes className="h-6 w-6" />}
          title={localize(lang, "Нет подов", "No pods")}
          description={localize(
            lang,
            "В этом namespace нет подов или фильтр ничего не нашёл.",
            "No pods in this namespace, or the filter matched nothing.",
          )}
        />
      ) : (
        <div className="divide-y divide-border/70">
          {attention.length ? (
            <PodGroup
              lang={lang}
              title={localize(lang, "Требуют внимания", "Needs attention")}
              pods={attention}
              selectedPodId={selectedPodId}
              onSelect={onSelect}
            />
          ) : null}
          {healthy.length ? (
            <PodGroup
              lang={lang}
              title={localize(lang, "В норме", "Healthy")}
              pods={healthy}
              selectedPodId={selectedPodId}
              onSelect={onSelect}
              quiet
            />
          ) : null}
        </div>
      )}
    </ContentPanel>
  );
}

function PodGroup({
  lang,
  title,
  pods,
  selectedPodId,
  onSelect,
  quiet = false,
}: {
  lang: string;
  title: string;
  pods: KubernetesPodRef[];
  selectedPodId: string;
  onSelect: (podId: string) => void;
  quiet?: boolean;
}) {
  return (
    <section>
      <div
        className={cn(
          "flex items-center justify-between px-4 py-2.5 sm:px-5",
          quiet ? "bg-transparent" : "bg-destructive/5",
        )}
      >
        <h3 className={cn("text-xs font-semibold uppercase tracking-wide", quiet ? "text-muted-foreground" : "text-destructive")}>
          {title}
        </h3>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">{pods.length}</span>
      </div>
      <ul role="listbox" aria-label={title} className="divide-y divide-border/60">
        {pods.map((pod) => {
          const selected = pod.id === selectedPodId;
          const ready = isPodReady(pod);
          return (
            <li key={pod.id}>
              <button
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                  "flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors sm:px-5",
                  selected ? "bg-primary/8" : "hover:bg-secondary/40",
                )}
                onClick={() => onSelect(pod.id)}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-foreground" title={pod.name}>
                      {pod.name}
                    </span>
                    <StatusBadge
                      label={pod.phase || pod.health}
                      tone={podPhaseTone(pod.phase, pod.health)}
                      className="shrink-0 normal-case tracking-normal"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{humanPodStatus(pod, lang)}</p>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
                    <span>
                      {ready
                        ? localize(lang, "Ready", "Ready")
                        : `${pod.ready_containers}/${pod.total_containers} ready`}
                    </span>
                    <span aria-hidden>·</span>
                    <span>
                      {pod.restart_count} {localize(lang, "рестартов", "restarts")}
                    </span>
                    {pod.node_name ? (
                      <>
                        <span aria-hidden>·</span>
                        <span className="truncate">{pod.node_name}</span>
                      </>
                    ) : null}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
