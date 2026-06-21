import type { Dispatch, SetStateAction } from "react";
import { RefreshCw, ScrollText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import type { FrontendServer, ServerMemoryOverviewResponse } from "@/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { MemoryOverviewSections } from "./MemoryOverviewSections";

type MemoryPolicyDraft = ServerMemoryOverviewResponse["policy"] | null;

type SettingsMemoryPanelProps = {
  memoryServers: FrontendServer[];
  selectedMemoryServerId: number | null;
  selectedMemoryServer: FrontendServer | null;
  memoryOverview?: ServerMemoryOverviewResponse;
  memoryLoading: boolean;
  memoryDreamRunning: boolean;
  memoryPolicySaving: boolean;
  memoryActionKey: string | null;
  memoryPolicyDraft: MemoryPolicyDraft;
  onSelectedMemoryServerIdChange: (serverId: number) => void;
  onMemoryPolicyDraftChange: Dispatch<SetStateAction<MemoryPolicyDraft>>;
  onRefreshMemoryOverview: () => void | Promise<void>;
  onRunMemoryDreams: () => void | Promise<void>;
  onSaveMemoryPolicy: () => void | Promise<void>;
  onArchiveMemorySnapshot: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToNote: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToSkill: (snapshotId: number) => void | Promise<void>;
};

function MemoryPolicyControls({
  memoryPolicyDraft,
  memoryPolicySaving,
  onMemoryPolicyDraftChange,
  onSaveMemoryPolicy,
}: {
  memoryPolicyDraft: MemoryPolicyDraft;
  memoryPolicySaving: boolean;
  onMemoryPolicyDraftChange: Dispatch<SetStateAction<MemoryPolicyDraft>>;
  onSaveMemoryPolicy: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  if (!memoryPolicyDraft) return null;

  return (
    <div className="space-y-4 rounded-xl border border-border bg-secondary/10 px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">Правила долгосрочной памяти</p>
        <Button size="sm" variant="outline" className="h-9" onClick={() => void onSaveMemoryPolicy()} disabled={memoryPolicySaving}>
          {memoryPolicySaving ? t("mem.saving") : t("mem.save")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-3 transition-colors hover:bg-secondary/30">
          <div>
            <p className="text-xs font-medium">Автозаметки</p>
            <p className="text-xs text-muted-foreground">Включить долгосрочную память</p>
          </div>
          <Switch
            checked={memoryPolicyDraft.ai_memory_enabled}
            onCheckedChange={(value) => onMemoryPolicyDraftChange((draft) => draft ? { ...draft, ai_memory_enabled: value } : null)}
          />
        </label>

        <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-3 transition-colors hover:bg-secondary/30">
          <div>
            <p className="text-xs font-medium">Операционная память</p>
            <p className="text-xs text-muted-foreground">Оперативный контекст</p>
          </div>
          <Switch
            checked={memoryPolicyDraft.operational_memory_enabled}
            onCheckedChange={(value) => onMemoryPolicyDraftChange((draft) => draft ? { ...draft, operational_memory_enabled: value } : null)}
          />
        </label>
      </div>
    </div>
  );
}

function MemoryServerSelector({
  memoryServers,
  selectedMemoryServerId,
  selectedMemoryServer,
  memoryOverview,
  onSelectedMemoryServerIdChange,
}: Pick<
  SettingsMemoryPanelProps,
  "memoryServers" | "selectedMemoryServerId" | "selectedMemoryServer" | "memoryOverview" | "onSelectedMemoryServerIdChange"
>) {
  const { t } = useI18n();

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
      <div className="space-y-1.5">
        <Label className="text-sm">Сервер</Label>
        <Select
          value={selectedMemoryServerId ? String(selectedMemoryServerId) : ""}
          onValueChange={(value) => onSelectedMemoryServerIdChange(Number(value))}
        >
          <SelectTrigger className="h-10">
            <SelectValue placeholder={t("mem.select_server")} />
          </SelectTrigger>
          <SelectContent>
            {memoryServers.map((server) => (
              <SelectItem key={server.id} value={String(server.id)}>
                {server.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="rounded-xl border border-border/60 bg-secondary/15 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{selectedMemoryServer?.name || t("mem.no_server")}</Badge>
          <Badge variant={memoryOverview?.daemon_state?.status === "running" ? "default" : "secondary"}>
            Служба консолидации: {memoryOverview?.daemon_state?.status === "running" ? "активна" : memoryOverview?.daemon_state?.status || "неизвестно"}
          </Badge>
          {memoryOverview?.daemon_state?.is_stale ? (
            <Badge variant="destructive">таймаут активности</Badge>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function SettingsMemoryPanel({
  memoryServers,
  selectedMemoryServerId,
  selectedMemoryServer,
  memoryOverview,
  memoryLoading,
  memoryDreamRunning,
  memoryPolicySaving,
  memoryActionKey,
  memoryPolicyDraft,
  onSelectedMemoryServerIdChange,
  onMemoryPolicyDraftChange,
  onRefreshMemoryOverview,
  onRunMemoryDreams,
  onSaveMemoryPolicy,
  onArchiveMemorySnapshot,
  onPromoteMemorySnapshotToNote,
  onPromoteMemorySnapshotToSkill,
}: SettingsMemoryPanelProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-6 pb-10">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <ScrollText className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Память AI по серверу</h1>
          <p className="text-sm leading-6 text-muted-foreground">{t("mem.subtitle")}</p>
        </div>
      </div>

      <SectionCard
        title="Панели долгосрочной памяти"
        icon={ScrollText}
        description={t("mem.section_desc")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-9 gap-1.5"
              onClick={() => void onRefreshMemoryOverview()}
              disabled={!selectedMemoryServerId || memoryLoading}
            >
              <RefreshCw className={cn("h-3 w-3", memoryLoading && "animate-spin")} />
              {t("mem.refresh")}
            </Button>
            <Button
              size="sm"
              className="h-9 gap-1.5"
              onClick={() => void onRunMemoryDreams()}
              disabled={!selectedMemoryServerId || memoryDreamRunning}
            >
              <RefreshCw className={cn("h-3 w-3", memoryDreamRunning && "animate-spin")} />
              {memoryDreamRunning ? "Консолидация..." : "Запустить консолидацию"}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <MemoryServerSelector
            memoryServers={memoryServers}
            selectedMemoryServerId={selectedMemoryServerId}
            selectedMemoryServer={selectedMemoryServer}
            memoryOverview={memoryOverview}
            onSelectedMemoryServerIdChange={onSelectedMemoryServerIdChange}
          />
          <MemoryPolicyControls
            memoryPolicyDraft={memoryPolicyDraft}
            memoryPolicySaving={memoryPolicySaving}
            onMemoryPolicyDraftChange={onMemoryPolicyDraftChange}
            onSaveMemoryPolicy={onSaveMemoryPolicy}
          />
          <MemoryOverviewSections
            memoryOverview={memoryOverview}
            selectedMemoryServerId={selectedMemoryServerId}
            memoryLoading={memoryLoading}
            memoryActionKey={memoryActionKey}
            onArchiveMemorySnapshot={onArchiveMemorySnapshot}
            onPromoteMemorySnapshotToNote={onPromoteMemorySnapshotToNote}
            onPromoteMemorySnapshotToSkill={onPromoteMemorySnapshotToSkill}
          />
        </div>
      </SectionCard>
    </div>
  );
}
