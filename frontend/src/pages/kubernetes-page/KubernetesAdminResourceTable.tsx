import { Boxes, Braces, Database } from "lucide-react";

import type {
  KubernetesAdminResourceCatalogItem,
  KubernetesAdminResourceItem,
  KubernetesAdminResourceListResponse,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { localize } from "@/lib/i18n";
import {
  OwnershipSummaryPanel,
  ownerLabel,
  ownerTone,
} from "@/pages/kubernetes-page/KubernetesAdminOwnershipPanel";
import {
  DEFAULT_NAMESPACE,
  type ResourceTarget,
  resourceApiVersion,
  resourceFreshness,
  resourceStatus,
  sameTarget,
  targetFromItem,
} from "@/pages/kubernetes-page/kubernetesAdminResourceModel";
import { statusLabel, statusTone } from "@/pages/kubernetes-page/kubernetesPageSections";

export function ResourceTablePanel({
  lang,
  selectedResource,
  namespace,
  namespaceForQuery,
  onNamespaceChange,
  nameFilter,
  onNameFilterChange,
  rows,
  response,
  loading,
  error,
  onRetry,
  selectedTarget,
  onSelectTarget,
}: {
  lang: string;
  selectedResource: KubernetesAdminResourceCatalogItem | null;
  namespace: string;
  namespaceForQuery: string;
  onNamespaceChange: (value: string) => void;
  nameFilter: string;
  onNameFilterChange: (value: string) => void;
  rows: KubernetesAdminResourceItem[];
  response?: KubernetesAdminResourceListResponse;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  selectedTarget: ResourceTarget | null;
  onSelectTarget: (target: ResourceTarget) => void;
}) {
  return (
    <SectionCard
      title={selectedResource ? selectedResource.kind : localize(lang, "Ресурсы", "Resources")}
      description={
        selectedResource
          ? `${selectedResource.query.api_version} / ${selectedResource.query.resource}`
          : localize(lang, "Выберите тип ресурса в каталоге.", "Select a resource from the catalog.")
      }
      icon={<Database className="h-4 w-4" />}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {response ? <StatusBadge label={`${response.item_count ?? rows.length} ${localize(lang, "объектов", "items")}`} tone="info" /> : null}
          {response?.truncated ? <StatusBadge label={localize(lang, "список обрезан", "truncated")} tone="warning" /> : null}
          {response?.ownership_summary ? <StatusBadge label={`${response.ownership_summary.guarded_items} ${localize(lang, "защищено", "guarded")}`} tone="warning" /> : null}
        </div>
      }
      bodyClassName="space-y-4"
    >
      <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
        <FieldLabel label={localize(lang, "Пространство имён", "Namespace")}>
          <Input
            value={selectedResource?.namespaced ? namespace : ""}
            disabled={!selectedResource?.namespaced}
            onChange={(event) => onNamespaceChange(event.target.value)}
            placeholder={selectedResource?.namespaced ? DEFAULT_NAMESPACE : localize(lang, "весь кластер", "cluster-scoped")}
            aria-label={localize(lang, "Пространство имён ресурса", "Resource namespace")}
          />
        </FieldLabel>
        <FieldLabel label={localize(lang, "Фильтр по имени", "Name filter")}>
          <Input
            value={nameFilter}
            onChange={(event) => onNameFilterChange(event.target.value)}
            placeholder={localize(lang, "payments-api, ingress, kube-system...", "payments-api, ingress, kube-system...")}
            aria-label={localize(lang, "Фильтр ресурсов по имени", "Resource name filter")}
          />
        </FieldLabel>
      </div>

      {response?.ownership_summary ? <OwnershipSummaryPanel lang={lang} summary={response.ownership_summary} /> : null}

      {loading ? (
        <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-8 text-sm text-muted-foreground">
          {localize(lang, "Загружаю ресурсы", "Loading resources")}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-4 text-sm text-destructive">
          <div>{error instanceof Error ? error.message : localize(lang, "Не удалось загрузить ресурсы", "Resource list failed")}</div>
          <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
            {localize(lang, "Повторить", "Retry")}
          </Button>
        </div>
      ) : rows.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{localize(lang, "Имя", "Name")}</TableHead>
              <TableHead>{localize(lang, "Пространство", "Namespace")}</TableHead>
              <TableHead>{localize(lang, "Состояние", "Status")}</TableHead>
              <TableHead>{localize(lang, "Владелец", "Owner")}</TableHead>
              <TableHead>{localize(lang, "Возраст / актуальность", "Age/Freshness")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.slice(0, 120).map((item, index) => {
              const target = targetFromItem(item, namespaceForQuery);
              const isSelected = selectedTarget ? sameTarget(target, selectedTarget) : false;
              const status = resourceStatus(item);
              const ownership = item.webterm_ownership;
              return (
                <TableRow
                  key={`${target.namespace}-${target.name}-${index}`}
                  data-state={isSelected ? "selected" : undefined}
                  className="cursor-pointer"
                  onClick={() => target.name && onSelectTarget(target)}
                >
                  <TableCell className="min-w-[220px]">
                    <div className="flex min-w-0 items-center gap-2">
                      {selectedResource?.custom ? <Braces className="h-4 w-4 text-primary" /> : <Boxes className="h-4 w-4 text-muted-foreground" />}
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-foreground">{target.name || "-"}</div>
                        <div className="truncate font-mono text-xs text-muted-foreground">{resourceApiVersion(item, selectedResource)}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[160px] truncate text-muted-foreground">
                    {target.namespace || localize(lang, "кластер", "cluster")}
                  </TableCell>
                  <TableCell>
                    <StatusBadge label={statusLabel(lang, status)} tone={statusTone(status)} />
                  </TableCell>
                  <TableCell>
                    {ownership ? (
                      <div className="flex flex-col gap-1">
                        <StatusBadge label={ownerLabel(ownership.owner, lang)} tone={ownerTone(ownership.owner)} />
                        <span className="max-w-[160px] truncate text-xs text-muted-foreground">{ownership.change_path}</span>
                      </div>
                    ) : (
                      <StatusBadge label={localize(lang, "неизвестно", "unknown")} tone="neutral" />
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{resourceFreshness(lang, item)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      ) : (
        <EmptyState
          icon={<Database className="h-5 w-5" />}
          title={localize(lang, "Ресурсы не найдены", "No resources found")}
          description={localize(
            lang,
            "Проверьте пространство имён, фильтр и права активной сессии.",
            "Check the namespace, name filter, or active session permissions.",
          )}
        />
      )}
    </SectionCard>
  );
}

function FieldLabel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
