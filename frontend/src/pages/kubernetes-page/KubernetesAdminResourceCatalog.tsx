import { Braces, ListTree, Search } from "lucide-react";

import type {
  KubernetesAdminResourceCatalogGroup,
  KubernetesAdminResourceCatalogItem,
} from "@/api";
import { Input } from "@/components/ui/input";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { cn } from "@/lib/utils";
import { localize } from "@/lib/i18n";

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
      title={localize(lang, "Catalog", "Catalog")}
      description={localize(lang, "Только backend resource_catalog, без угадывания API paths.", "Backend resource_catalog only, no API path guessing.")}
      icon={<ListTree className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="pl-9"
          placeholder={localize(lang, "Pods, deploy, widgets...", "Pods, deploy, widgets...")}
          aria-label="Resource catalog search"
        />
      </div>

      <div className="space-y-1.5">
        <button type="button" className={catalogGroupClass(!selectedGroupId)} onClick={() => onSelectGroup("")}>
          <span>{localize(lang, "Все ресурсы", "All resources")}</span>
          <span className="font-mono text-[11px] text-muted-foreground">{items.length}</span>
        </button>
        {groups.map((group) => (
          <button
            key={group.id}
            type="button"
            className={catalogGroupClass(selectedGroupId === group.id)}
            onClick={() => onSelectGroup(group.id)}
          >
            <span className="truncate">{group.label}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{group.item_count}</span>
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
                  <div className="mt-1 truncate font-mono text-[11px]">{item.resource}</div>
                </div>
                {item.custom ? <Braces className="h-4 w-4 text-primary" /> : null}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusBadge label={item.scope} tone="neutral" dot={false} />
                {item.custom ? <StatusBadge label="CRD" tone="info" dot={false} /> : null}
                {item.safe_read_actions.slice(0, 3).map((action) => (
                  <StatusBadge key={action} label={action} tone="neutral" dot={false} />
                ))}
                {item.has_mutating_verbs ? <StatusBadge label="mutating verbs" tone="warning" dot={false} /> : null}
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
