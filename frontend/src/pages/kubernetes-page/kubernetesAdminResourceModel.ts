import type {
  KubernetesAdminResourceCatalogItem,
  KubernetesAdminResourceItem,
  KubernetesAdminSession,
  KubernetesCluster,
} from "@/api";
import { localize } from "@/lib/i18n";
import { formatSync } from "@/pages/kubernetes-page/kubernetesPageSections";

export const DEFAULT_NAMESPACE = "default";

export type InspectorTab = "summary" | "yaml" | "events" | "logs" | "watch";

export type ResourceTarget = {
  name: string;
  namespace: string;
};

type ResourceItemWithSummary = KubernetesAdminResourceItem & {
  summary?: Record<string, unknown>;
};

export function activeSessionForCluster(
  sessions: KubernetesAdminSession[],
  cluster: KubernetesCluster | undefined,
  preferredId: string,
) {
  const active = sessions.filter((session) => session.status === "active" && session.mode === "read");
  if (preferredId) {
    const preferred = active.find((session) => session.id === preferredId);
    if (preferred) return preferred;
  }
  return active.find((session) => !session.cluster_id || session.cluster_id === cluster?.id) || active[0] || null;
}

export function buildResourceQuery(
  sessionId: string,
  item: KubernetesAdminResourceCatalogItem,
  namespace: string,
  name?: string,
  extra: Record<string, unknown> = {},
) {
  return {
    session_id: sessionId,
    ...item.query,
    namespace: item.namespaced ? namespace : "",
    ...(name ? { name } : {}),
    ...extra,
  };
}

export function filterCatalogItems(
  items: KubernetesAdminResourceCatalogItem[],
  groupId: string,
  search: string,
) {
  const needle = search.trim().toLowerCase();
  return items.filter((item) => {
    if (groupId && item.ui_group !== groupId) return false;
    if (!needle) return true;
    return [
      item.kind,
      item.resource,
      item.api_version,
      item.group,
      item.version,
      item.scope,
      item.short_names.join(" "),
      item.categories.join(" "),
      item.crd_name || "",
    ].join(" ").toLowerCase().includes(needle);
  });
}

export function filterResourceRows(items: KubernetesAdminResourceItem[], nameFilter: string) {
  const needle = nameFilter.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => {
    const target = targetFromItem(item, "");
    return [
      target.name,
      target.namespace,
      resourceKind(item, null),
      resourceStatus(item),
      item.webterm_ownership?.owner || "",
      item.webterm_ownership?.change_path || "",
    ].join(" ").toLowerCase().includes(needle);
  });
}

export function targetFromItem(item: KubernetesAdminResourceItem, fallbackNamespace: string): ResourceTarget {
  const metadata = metadataOf(item);
  return {
    name: stringValue(metadata.name) || stringValue(item.name),
    namespace: stringValue(metadata.namespace) || fallbackNamespace || "",
  };
}

export function sameTarget(left: ResourceTarget, right: ResourceTarget) {
  return left.name === right.name && (left.namespace || "") === (right.namespace || "");
}

export function metadataOf(item: Record<string, unknown>) {
  return objectValue(item.metadata);
}

export function resourceKind(item: Record<string, unknown>, selectedResource: KubernetesAdminResourceCatalogItem | null) {
  return stringValue(item.kind) || selectedResource?.kind || "-";
}

export function resourceApiVersion(item: Record<string, unknown>, selectedResource: KubernetesAdminResourceCatalogItem | null) {
  return stringValue(item.apiVersion) || stringValue(item.api_version) || selectedResource?.query.api_version || "-";
}

export function resourceStatus(item: Record<string, unknown>) {
  const row = item as ResourceItemWithSummary;
  const summary = objectValue(row.summary);
  const status = objectValue(item.status);
  const candidates = [
    summary.health,
    summary.status,
    summary.phase,
    summary.ready_status,
    status.phase,
    status.status,
    status.reason,
  ].map(stringValue).filter(Boolean);
  const value = candidates[0] || "unknown";
  const normalized = value.toLowerCase();
  if (["true", "ready", "running", "healthy", "active", "bound"].includes(normalized)) return "healthy";
  if (["false", "failed", "error", "degraded", "crashloopbackoff"].includes(normalized)) return "degraded";
  if (["pending", "unknown", "progressing", "warning"].includes(normalized)) return "warning";
  return normalized || "unknown";
}

export function resourceFreshness(lang: string, item: Record<string, unknown>) {
  const metadata = metadataOf(item);
  const created =
    stringValue(metadata.creationTimestamp) ||
    stringValue(metadata.creation_timestamp) ||
    stringValue(item.created_at);
  if (created) return formatSync(lang, created);
  const resourceVersion = stringValue(metadata.resourceVersion) || stringValue(item.resource_version);
  return resourceVersion ? `rv ${resourceVersion}` : localize(lang, "нет данных", "no data");
}

export function resourceFactRows(resource: Record<string, unknown>) {
  const metadata = metadataOf(resource);
  const status = objectValue(resource.status);
  const spec = objectValue(resource.spec);
  const rows: Array<[string, string]> = [
    ["Kind", stringValue(resource.kind) || "-"],
    ["API version", stringValue(resource.apiVersion) || stringValue(resource.api_version) || "-"],
    ["Name", stringValue(metadata.name) || "-"],
    ["Namespace", stringValue(metadata.namespace) || "cluster"],
    ["Resource version", stringValue(metadata.resourceVersion) || "-"],
    ["Created", stringValue(metadata.creationTimestamp) || "-"],
  ];
  const phase = stringValue(status.phase) || stringValue(status.status);
  const replicas = stringValue(spec.replicas);
  if (phase) rows.push(["Status", phase]);
  if (replicas) rows.push(["Replicas", replicas]);
  return rows.slice(0, 10);
}

export function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function stringValue(value: unknown) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}
