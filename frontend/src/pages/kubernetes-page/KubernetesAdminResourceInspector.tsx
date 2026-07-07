import { Activity, AlertTriangle, FileCode2, ScrollText } from "lucide-react";

import type {
  KubernetesAdminPodLogsResponse,
  KubernetesAdminResourceCatalogItem,
  KubernetesAdminResourceDetailResponse,
  KubernetesAdminResourceItem,
  KubernetesAdminResourceWatchResponse,
  KubernetesAdminResourceYamlResponse,
} from "@/api";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { localize } from "@/lib/i18n";
import { AdminLogsSnapshotPanel } from "@/pages/kubernetes-page/KubernetesAdminLogsPanel";
import {
  OwnershipPanel,
  ownerLabel,
  ownerTone,
} from "@/pages/kubernetes-page/KubernetesAdminOwnershipPanel";
import { WatchPreviewPanel } from "@/pages/kubernetes-page/KubernetesAdminWatchPanel";
import {
  type InspectorTab,
  type ResourceTarget,
  resourceFactRows,
} from "@/pages/kubernetes-page/kubernetesAdminResourceModel";

export function ResourceInspector({
  lang,
  selectedResource,
  selectedTarget,
  selectedRow,
  tab,
  onTabChange,
  detail,
  detailLoading,
  detailError,
  yaml,
  yamlLoading,
  yamlError,
  logs,
  logsLoading,
  logsError,
  watch,
  watchLoading,
  watchError,
}: {
  lang: string;
  selectedResource: KubernetesAdminResourceCatalogItem | null;
  selectedTarget: ResourceTarget | null;
  selectedRow: KubernetesAdminResourceItem | null;
  tab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  detail?: KubernetesAdminResourceDetailResponse;
  detailLoading: boolean;
  detailError: unknown;
  yaml?: KubernetesAdminResourceYamlResponse;
  yamlLoading: boolean;
  yamlError: unknown;
  logs?: KubernetesAdminPodLogsResponse;
  logsLoading: boolean;
  logsError: unknown;
  watch?: KubernetesAdminResourceWatchResponse;
  watchLoading: boolean;
  watchError: unknown;
}) {
  const canLogs = selectedResource?.kind === "Pod" && selectedResource.safe_read_actions.includes("logs");
  const canWatch = Boolean(selectedResource?.safe_read_actions.includes("watch"));

  return (
    <SectionCard
      title={localize(lang, "Inspector", "Inspector")}
      description={
        selectedTarget
          ? `${selectedResource?.kind || "Resource"} / ${selectedTarget.namespace || "cluster"} / ${selectedTarget.name}`
          : localize(lang, "Выберите строку в таблице.", "Select a row in the table.")
      }
      icon={<FileCode2 className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      {!selectedResource || !selectedTarget ? (
        <EmptyState
          icon={<FileCode2 className="h-5 w-5" />}
          title={localize(lang, "Объект не выбран", "No object selected")}
          description={localize(
            lang,
            "Выберите resource row, чтобы открыть summary, YAML, events, logs или watch preview.",
            "Select a resource row to open summary, YAML, events, logs, or watch preview.",
          )}
        />
      ) : (
        <>
          <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge label={selectedResource.kind} tone="info" />
              <StatusBadge label={selectedTarget.namespace || localize(lang, "cluster", "cluster")} tone="neutral" />
              {selectedRow?.webterm_ownership ? (
                <StatusBadge
                  label={ownerLabel(selectedRow.webterm_ownership.owner)}
                  tone={ownerTone(selectedRow.webterm_ownership.owner)}
                />
              ) : null}
              {selectedResource.custom ? <StatusBadge label="CRD" tone="info" /> : null}
            </div>
            <h3 className="mt-2 break-all text-sm font-semibold text-foreground">{selectedTarget.name}</h3>
            <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
              {selectedResource.query.api_version} / {selectedResource.query.resource}
            </div>
          </div>

          <Tabs value={tab} onValueChange={(value) => onTabChange(value as InspectorTab)}>
            <TabsList className="grid h-auto w-full grid-cols-3 gap-1 p-1 text-xs xl:grid-cols-5">
              <TabsTrigger value="summary" className="text-xs">
                Summary
              </TabsTrigger>
              <TabsTrigger value="yaml" className="text-xs">
                YAML
              </TabsTrigger>
              <TabsTrigger value="events" className="text-xs">
                Events
              </TabsTrigger>
              <TabsTrigger value="logs" className="text-xs" disabled={!canLogs}>
                Logs
              </TabsTrigger>
              <TabsTrigger value="watch" className="text-xs" disabled={!canWatch}>
                Watch
              </TabsTrigger>
            </TabsList>

            <TabsContent value="summary">
              <ResourceSummaryView
                lang={lang}
                detail={detail}
                loading={detailLoading}
                error={detailError}
                selectedRow={selectedRow}
              />
            </TabsContent>
            <TabsContent value="yaml">
              <YamlView lang={lang} yaml={yaml} loading={yamlLoading} error={yamlError} />
            </TabsContent>
            <TabsContent value="events">
              <EventsView lang={lang} detail={detail} loading={detailLoading} error={detailError} />
            </TabsContent>
            <TabsContent value="logs">
              <LogsView lang={lang} logs={logs} loading={logsLoading} error={logsError} />
            </TabsContent>
            <TabsContent value="watch">
              <WatchView lang={lang} watch={watch} loading={watchLoading} error={watchError} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </SectionCard>
  );
}

function ResourceSummaryView({
  lang,
  detail,
  loading,
  error,
  selectedRow,
}: {
  lang: string;
  detail?: KubernetesAdminResourceDetailResponse;
  loading: boolean;
  error: unknown;
  selectedRow: KubernetesAdminResourceItem | null;
}) {
  if (loading) return <PanelLoading text={localize(lang, "Загружаю detail", "Loading detail")} />;
  if (error) return <PanelError lang={lang} error={error} />;

  const facts = detail?.resource || selectedRow || {};
  const ownership = detail?.ownership || selectedRow?.webterm_ownership;
  return (
    <div className="space-y-3">
      {ownership ? <OwnershipPanel lang={lang} ownership={ownership} /> : null}
      <div className="grid gap-2 sm:grid-cols-2">
        {resourceFactRows(facts).map(([label, value]) => (
          <div key={label} className="rounded-lg border border-border/70 bg-background/45 px-3 py-3">
            <div className="text-xs font-medium text-muted-foreground">{label}</div>
            <div className="mt-1 break-all text-sm font-semibold text-foreground">{value}</div>
          </div>
        ))}
      </div>
      {detail?.policy ? (
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={detail.policy.mutates_state ? "mutates" : "read-only"} tone={detail.policy.mutates_state ? "danger" : "success"} />
            {detail.policy.blocked_actions.slice(0, 8).map((action) => (
              <StatusBadge key={action} label={action} tone="neutral" dot={false} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function YamlView({
  lang,
  yaml,
  loading,
  error,
}: {
  lang: string;
  yaml?: KubernetesAdminResourceYamlResponse;
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PanelLoading text={localize(lang, "Загружаю YAML", "Loading YAML")} />;
  if (error) return <PanelError lang={lang} error={error} />;
  if (!yaml) {
    return (
      <EmptyState
        icon={<FileCode2 className="h-5 w-5" />}
        title="YAML"
        description={localize(lang, "Откройте вкладку, чтобы загрузить redacted YAML.", "Open the tab to load redacted YAML.")}
      />
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={yaml.mode} tone="success" />
        {yaml.redacted ? <StatusBadge label="redacted" tone="warning" /> : null}
        <StatusBadge label={yaml.policy.mutates_state ? "mutates" : "read-only"} tone={yaml.policy.mutates_state ? "danger" : "success"} />
      </div>
      <pre className="max-h-[34rem] overflow-auto rounded-lg border border-border/70 bg-secondary/25 p-4 text-xs leading-5 text-foreground">
        {JSON.stringify(yaml.resource, null, 2)}
      </pre>
    </div>
  );
}

function EventsView({
  lang,
  detail,
  loading,
  error,
}: {
  lang: string;
  detail?: KubernetesAdminResourceDetailResponse;
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PanelLoading text={localize(lang, "Загружаю events", "Loading events")} />;
  if (error) return <PanelError lang={lang} error={error} />;
  const events = detail?.events?.events || [];
  return events.length ? (
    <div className="space-y-2">
      {events.map((event, index) => (
        <div key={`${event.name}-${event.resource_version}-${index}`} className="rounded-lg border border-border/70 bg-background/45 px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={event.type || "event"} tone={event.type === "Warning" ? "warning" : "info"} />
            <span className="text-sm font-semibold text-foreground">{event.reason || event.name}</span>
            {event.count > 1 ? <StatusBadge label={`x${event.count}`} tone="neutral" /> : null}
          </div>
          <div className="mt-2 text-xs leading-5 text-muted-foreground">{event.message || "-"}</div>
          <div className="mt-2 text-xs text-muted-foreground">{event.last_timestamp || event.event_time || "-"}</div>
        </div>
      ))}
    </div>
  ) : (
    <EmptyState
      icon={<AlertTriangle className="h-5 w-5" />}
      title={localize(lang, "Events не найдены", "No events found")}
      description={localize(lang, "Для выбранного объекта backend вернул пустой bounded events snapshot.", "The backend returned an empty bounded events snapshot for the selected object.")}
    />
  );
}

function LogsView({
  lang,
  logs,
  loading,
  error,
}: {
  lang: string;
  logs?: KubernetesAdminPodLogsResponse;
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PanelLoading text={localize(lang, "Загружаю logs snapshot", "Loading logs snapshot")} />;
  if (error) return <PanelError lang={lang} error={error} />;
  return logs ? (
    <AdminLogsSnapshotPanel lang={lang} logs={logs} />
  ) : (
    <EmptyState
      icon={<ScrollText className="h-5 w-5" />}
      title="Logs snapshot"
      description={localize(lang, "Logs доступны только для Pod и загружаются bounded snapshot.", "Logs are available for Pods only and load as a bounded snapshot.")}
    />
  );
}

function WatchView({
  lang,
  watch,
  loading,
  error,
}: {
  lang: string;
  watch?: KubernetesAdminResourceWatchResponse;
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PanelLoading text={localize(lang, "Загружаю watch preview", "Loading watch preview")} />;
  if (error) return <PanelError lang={lang} error={error} />;
  return watch ? (
    <WatchPreviewPanel lang={lang} watch={watch} />
  ) : (
    <EmptyState
      icon={<Activity className="h-5 w-5" />}
      title="Watch preview"
      description={localize(lang, "Это bounded preview, не unrestricted stream.", "This is a bounded preview, not an unrestricted stream.")}
    />
  );
}

function PanelLoading({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-8 text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function PanelError({ lang, error }: { lang: string; error: unknown }) {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-4 text-sm text-destructive">
      {error instanceof Error ? error.message : localize(lang, "Request failed", "Request failed")}
    </div>
  );
}
