import { Braces, ListTree, Search } from "lucide-react";

import type {
  KubernetesAdminResourceCatalogGroup,
  KubernetesAdminResourceCatalogItem,
} from "@/api";
import { Input } from "@/components/ui/input";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";
import { localize } from "@/lib/i18n";

function scopeLabel(lang: string, scope: string) {
  const normalized = scope.toLowerCase();
  if (normalized === "namespaced") return localize(lang, "в пространстве имён", "namespaced");
  if (normalized === "cluster" || normalized === "cluster-scoped") return localize(lang, "весь кластер", "cluster scoped");
  return scope;
}

function readActionLabel(lang: string, action: string) {
  const labels: Record<string, [string, string]> = {
    get: ["открыть", "get"],
    list: ["список", "list"],
    detail: ["подробности", "details"],
    watch: ["наблюдение", "watch"],
    logs: ["логи", "logs"],
    yaml: ["YAML", "YAML"],
  };
  const label = labels[action.toLowerCase()];
  return label ? localize(lang, label[0], label[1]) : action;
}

export function ResourceCatalogPanel({
  lang,
  groups,
  items,
  visibleItems,
  selectedGroupId,
  selectedResource,
  search,
  onSearchChange,
  onSelectGroup,
  onSelectResource,
}: {
  lang: string;
  groups: KubernetesAdminResourceCatalogGroup[];
  items: KubernetesAdminResourceCatalogItem[];
  visibleItems: KubernetesAdminResourceCatalogItem[];
  selectedGroupId: string;
  selectedResource: KubernetesAdminResourceCatalogItem | null;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectGroup: (groupId: string) => void;
  onSelectResource: (item: KubernetesAdminResourceCatalogItem) => void;
}) {
  return (
    <SectionCard
      title={localize(lang, "Каталог ресурсов", "Resource catalog")}
      description={localize(lang, "Доступные типы ресурсов Kubernetes.", "Available Kubernetes resource types.")}
      icon={<ListTree className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="pl-9"
          placeholder={localize(lang, "Поды, развёртывания, виджеты...", "Pods, deploy, widgets...")}
          aria-label={localize(lang, "Поиск по каталогу ресурсов", "Resource catalog search")}
        />
      </div>

      <div className="space-y-1.5">
        <button type="button" className={catalogGroupClass(!selectedGroupId)} onClick={() => onSelectGroup("")}>
          <span>{localize(lang, "Все ресурсы", "All resources")}</span>
          <span className="font-mono text-2xs text-muted-foreground">{items.length}</span>
        </button>
        {groups.map((group) => (
          <button
            key={group.id}
            type="button"
            className={catalogGroupClass(selectedGroupId === group.id)}
            onClick={() => onSelectGroup(group.id)}
          >
            <span className="truncate">{group.label}</span>
            <span className="font-mono text-2xs text-muted-foreground">{group.item_count}</span>
          </button>
        ))}
      </div>

      <div className="max-h-[30rem] space-y-2 overflow-auto pr-1">
        {visibleItems.length ? (
          visibleItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                "w-full rounded-lg border px-3 py-3 text-left transition-colors",
                selectedResource?.id === item.id
                  ? "border-primary/45 bg-primary/10 text-foreground"
                  : "border-border/70 bg-background/45 text-muted-foreground hover:bg-secondary/45 hover:text-foreground",
              )}
              onClick={() => onSelectResource(item)}
            >
              <div className="flex min-w-0 items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{item.kind}</div>
                  <div className="mt-1 truncate font-mono text-2xs">{item.resource}</div>
                </div>
                {item.custom ? <Braces className="h-4 w-4 text-primary" /> : null}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusBadge label={scopeLabel(lang, item.scope)} tone="neutral" dot={false} />
                {item.custom ? <StatusBadge label="CRD" tone="info" dot={false} /> : null}
                {item.safe_read_actions.slice(0, 3).map((action) => (
                  <StatusBadge key={action} label={readActionLabel(lang, action)} tone="neutral" dot={false} />
                ))}
                {item.has_mutating_verbs ? <StatusBadge label={localize(lang, "есть изменяющие действия", "mutating verbs")} tone="warning" dot={false} /> : null}
              </div>
            </button>
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-border/60 bg-secondary/20 px-4 py-8 text-center text-xs text-muted-foreground">
            {localize(lang, "Ресурсы не найдены", "No resources found")}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function catalogGroupClass(active: boolean) {
  return cn(
    "flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-xs font-semibold transition-colors",
    active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
  );
}
