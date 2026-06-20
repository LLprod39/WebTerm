import { Layers, Plus, Settings, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { FrontendGroup } from "@/lib/api";

type ServerGroupsTabProps = {
  manageableGroups: FrontendGroup[];
  groupCount: number;
  t: (key: string) => string;
  tr: (key: string, vars?: Record<string, string | number>) => string;
  onOpenCreateGroup: () => void;
  onOpenGroupRules: (groupId: number) => void;
  onOpenGroupSettings: (group: FrontendGroup) => void;
  onRequestDeleteGroup: (group: FrontendGroup) => void;
};

export function ServerGroupsTab({
  manageableGroups,
  groupCount,
  t,
  tr,
  onOpenCreateGroup,
  onOpenGroupRules,
  onOpenGroupSettings,
  onRequestDeleteGroup,
}: ServerGroupsTabProps) {
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground">{t("srv.groups")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr("srv.groups_count", { count: groupCount })}
          </p>
        </div>
        <Button size="sm" className="h-10 gap-1.5 self-start sm:self-auto" onClick={onOpenCreateGroup}>
          <Plus className="h-3.5 w-3.5" /> {t("srv.create_group")}
        </Button>
      </div>

      {manageableGroups.length ? (
        <div>
          {manageableGroups.map((group, index) => (
            <article
              key={group.id!}
              className={`flex items-center gap-4 px-4 py-3 transition-colors hover:bg-secondary/30 ${
                index < manageableGroups.length - 1 ? "border-b border-border/50" : ""
              }`}
            >
              <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/70 bg-secondary/30">
                <Layers className="h-4 w-4 text-primary/80" />
                <span
                  className="absolute bottom-1 right-1 h-2 w-2 rounded-full border border-card"
                  style={{ backgroundColor: group.color }}
                  aria-hidden="true"
                />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{group.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {group.description || t("srv.group_description_empty")} ·{" "}
                  {tr("srv.servers_count_value", { count: group.server_count })}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  size="xs"
                  variant="outline"
                  className="h-9 gap-1.5 border-border hover:border-primary hover:text-primary"
                  onClick={() => onOpenGroupRules(group.id!)}
                >
                  <Layers className="h-3 w-3" /> {t("srv.rules_tab")}
                </Button>
                {group.can_edit ? (
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-9 w-9 border-border hover:border-primary hover:text-primary"
                    onClick={() => onOpenGroupSettings(group)}
                    aria-label={`${t("nav.settings")} ${group.name}`}
                    title={t("nav.settings")}
                  >
                    <Settings className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
                {group.role === "owner" ? (
                  <Button
                    size="icon"
                    variant="destructive"
                    className="h-9 w-9"
                    onClick={() => onRequestDeleteGroup(group)}
                    aria-label={`${t("srv.delete")} ${group.name}`}
                    title={t("srv.delete")}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="px-4 py-10 text-center">
          <h3 className="text-sm font-medium text-foreground">{t("srv.groups_empty_title")}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{t("srv.groups_empty_text")}</p>
        </div>
      )}
    </section>
  );
}
