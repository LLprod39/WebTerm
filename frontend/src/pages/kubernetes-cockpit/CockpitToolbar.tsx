import { ListFilter, Search, X } from "lucide-react";

import type { KubernetesCluster, KubernetesNamespaceSummary } from "@/api";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { localize } from "@/lib/i18n";

export function CockpitToolbar({
  lang,
  clusters,
  namespaces,
  clusterId,
  namespace,
  search,
  clustersLoading,
  namespacesLoading,
  podsShown,
  podsTotal,
  showSearch = true,
  onClusterChange,
  onNamespaceChange,
  onSearchChange,
}: {
  lang: string;
  clusters: KubernetesCluster[];
  namespaces: KubernetesNamespaceSummary[];
  clusterId: string;
  namespace: string;
  search: string;
  clustersLoading: boolean;
  namespacesLoading: boolean;
  podsShown: number;
  podsTotal: number;
  showSearch?: boolean;
  onClusterChange: (clusterId: string) => void;
  onNamespaceChange: (namespace: string) => void;
  onSearchChange: (value: string) => void;
}) {
  return (
    <div
      data-ui-slot="cockpit-toolbar"
      className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center lg:justify-end"
    >
      {showSearch ? (
        <span aria-live="polite" className="hidden whitespace-nowrap px-1 text-xs text-muted-foreground 2xl:inline">
          {podsTotal
            ? podsShown === podsTotal
              ? localize(lang, `${podsTotal} подов`, `${podsTotal} pods`)
              : localize(lang, `Показано ${podsShown} из ${podsTotal}`, `${podsShown} of ${podsTotal} shown`)
            : localize(lang, "Нет подов", "No pods")}
        </span>
      ) : null}

      <Select
        value={clusterId || "__none__"}
        onValueChange={(value) => {
          if (value === "__none__") return;
          onClusterChange(value);
        }}
        disabled={clustersLoading || clusters.length === 0}
      >
        <SelectTrigger
          className="h-9 w-full rounded-sm bg-card text-sm sm:w-44"
          aria-label={localize(lang, "Кластер", "Cluster")}
        >
          <ListFilter className="mr-2 h-3.5 w-3.5 text-muted-foreground" aria-hidden />
          <SelectValue
            placeholder={
              clustersLoading
                ? localize(lang, "Загрузка…", "Loading…")
                : localize(lang, "Кластер", "Cluster")
            }
          />
        </SelectTrigger>
        <SelectContent>
          {!clusterId ? (
            <SelectItem value="__none__" disabled>
              {localize(lang, "Выберите кластер", "Select cluster")}
            </SelectItem>
          ) : null}
          {clusters.map((cluster) => (
            <SelectItem key={cluster.id} value={cluster.id}>
              {cluster.name}
              {cluster.access_origin === "owned"
                ? localize(lang, " · мой", " · mine")
                : cluster.access_origin === "granted"
                  ? localize(lang, " · выдан", " · granted")
                  : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={namespace || "__none__"}
        onValueChange={(value) => {
          if (value === "__none__") return;
          onNamespaceChange(value);
        }}
        disabled={!clusterId || namespacesLoading || namespaces.length === 0}
      >
        <SelectTrigger
          className="h-9 w-full rounded-sm bg-card text-sm sm:w-44"
          aria-label={localize(lang, "Namespace", "Namespace")}
        >
          <SelectValue
            placeholder={
              !clusterId
                ? localize(lang, "Сначала кластер", "Cluster first")
                : namespacesLoading
                  ? localize(lang, "Загрузка…", "Loading…")
                  : localize(lang, "Namespace", "Namespace")
            }
          />
        </SelectTrigger>
        <SelectContent>
          {!namespace ? (
            <SelectItem value="__none__" disabled>
              {localize(lang, "Выберите namespace", "Select namespace")}
            </SelectItem>
          ) : null}
          {namespaces.map((ns) => (
            <SelectItem key={ns.id || ns.name} value={ns.name}>
              {ns.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {showSearch ? (
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label={localize(lang, "Поиск по подам", "Search pods")}
            placeholder={localize(lang, "Имя пода, фаза, нода…", "Pod name, phase, node…")}
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            className="h-9 rounded-sm bg-card pl-9 pr-9 text-sm"
            disabled={!namespace}
          />
          {search ? (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label={localize(lang, "Очистить поиск", "Clear search")}
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
