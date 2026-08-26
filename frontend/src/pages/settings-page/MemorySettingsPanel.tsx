import type { Dispatch, SetStateAction } from "react";
import { RefreshCw, Save, ScrollText, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { type FrontendServer, type ServerMemoryOverviewResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MemoryOverviewPanels } from "./MemoryOverviewPanels";
import { SectionCard } from "./SectionCard";

type MemoryPolicy = ServerMemoryOverviewResponse["policy"];

type MemorySettingsPanelProps = {
  memoryServers: FrontendServer[];
  selectedMemoryServerId: number | null;
  selectedMemoryServer: FrontendServer | null;
  memoryOverview: ServerMemoryOverviewResponse | undefined;
  memoryLoading: boolean;
  memoryDreamRunning: boolean;
  memoryPolicySaving: boolean;
  memoryActionKey: string | null;
  memoryPolicyDraft: MemoryPolicy | null;
  onSelectedMemoryServerIdChange: (serverId: number) => void;
  onMemoryPolicyDraftChange: Dispatch<SetStateAction<MemoryPolicy | null>>;
  onRefreshMemoryOverview: () => void | Promise<void>;
  onRunMemoryDreams: () => void | Promise<void>;
  onSaveMemoryPolicy: () => void | Promise<void>;
  onArchiveMemorySnapshot: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToNote: (snapshotId: number) => void | Promise<void>;
  onPromoteMemorySnapshotToSkill: (snapshotId: number) => void | Promise<void>;
};

export function MemorySettingsPanel({
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
}: MemorySettingsPanelProps) {
  const updatePolicy = <Key extends keyof MemoryPolicy>(key: Key, value: MemoryPolicy[Key]) => {
    onMemoryPolicyDraftChange((current) => (current ? { ...current, [key]: value } : current));
  };

  return (
    <SectionCard
      title="Долгосрочная память"
      icon={ScrollText}
      description="Сбор, проверка и объединение полезных записей."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 h-7"
            onClick={() => void onRefreshMemoryOverview()}
            disabled={!selectedMemoryServerId || memoryLoading}
          >
            <RefreshCw className={cn("h-3 w-3", memoryLoading && "animate-spin")} />
            Обновить
          </Button>
          <Button
            size="sm"
            className="gap-1.5 h-7"
            onClick={() => void onRunMemoryDreams()}
            disabled={!selectedMemoryServerId || memoryDreamRunning}
          >
            <Sparkles className={cn("h-3 w-3", memoryDreamRunning && "animate-spin")} />
            {memoryDreamRunning ? "Объединение…" : "Объединить записи"}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
          <div className="space-y-1.5">
            <Label className="text-xs">Сервер</Label>
            <Select
              value={selectedMemoryServerId ? String(selectedMemoryServerId) : ""}
              onValueChange={(value) => onSelectedMemoryServerIdChange(Number(value))}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Выбери сервер" />
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
              <Badge variant="outline">{selectedMemoryServer?.name || "Сервер не выбран"}</Badge>
              <Badge variant={memoryOverview?.daemon_state?.status === "running" ? "default" : "secondary"}>
                Служба: {memoryOverview?.daemon_state?.status === "running" ? "работает" : memoryOverview?.daemon_state?.status || "неизвестно"}
              </Badge>
              {memoryOverview?.daemon_state?.is_stale ? <Badge variant="outline">нет отклика</Badge> : null}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Здесь настраивается автоматическая память. Ручные заметки остаются в карточке сервера.
            </p>
            {memoryOverview?.daemon_state?.heartbeat_at ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Последний отклик: {new Date(memoryOverview.daemon_state.heartbeat_at).toLocaleString()}
              </p>
            ) : null}
          </div>
        </div>

        {memoryPolicyDraft ? (
          <div className="rounded-xl border border-border/60 bg-background/40 p-4 space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Правила памяти</p>
                <p className="text-xs text-muted-foreground">
                  Определяет, когда объединять записи и что сохранять в памяти сервера.
                </p>
              </div>
              <Button
                size="sm"
                className="h-8 px-4"
                onClick={() => void onSaveMemoryPolicy()}
                disabled={memoryPolicySaving || !selectedMemoryServerId}
              >
                <Save className="mr-1 h-3 w-3" />
                {memoryPolicySaving ? "Сохранение…" : "Сохранить правила"}
              </Button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Режим объединения</Label>
                <Select
                  value={memoryPolicyDraft.dream_mode}
                  onValueChange={(value) => updatePolicy("dream_mode", value as MemoryPolicy["dream_mode"])}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="heuristic">По правилам</SelectItem>
                    <SelectItem value="nightly_llm">Ночная обработка</SelectItem>
                    <SelectItem value="hybrid">Комбинированный</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Модель для ночной обработки</Label>
                <Input
                  value={memoryPolicyDraft.nightly_model_alias}
                  onChange={(event) => updatePolicy("nightly_model_alias", event.target.value)}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Событий до объединения</Label>
                <Input
                  type="number"
                  min={2}
                  max={50}
                  value={memoryPolicyDraft.nearline_event_threshold}
                  onChange={(event) => updatePolicy("nearline_event_threshold", Number(event.target.value || 2))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Начало ночного окна</Label>
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={memoryPolicyDraft.sleep_start_hour}
                  onChange={(event) => updatePolicy("sleep_start_hour", Number(event.target.value || 0))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Конец ночного окна</Label>
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={memoryPolicyDraft.sleep_end_hour}
                  onChange={(event) => updatePolicy("sleep_end_hour", Number(event.target.value || 0))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Хранить события, дней</Label>
                <Input
                  type="number"
                  min={7}
                  max={365}
                  value={memoryPolicyDraft.raw_event_retention_days}
                  onChange={(event) => updatePolicy("raw_event_retention_days", Number(event.target.value || 7))}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Хранить сессии, дней</Label>
                <Input
                  type="number"
                  min={14}
                  max={365}
                  value={memoryPolicyDraft.episode_retention_days}
                  onChange={(event) => updatePolicy("episode_retention_days", Number(event.target.value || 14))}
                  className="h-9"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={memoryPolicyDraft.is_enabled}
                  onChange={(event) => updatePolicy("is_enabled", event.target.checked)}
                />
                Долгосрочная память
              </label>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={memoryPolicyDraft.human_habits_capture_enabled}
                  onChange={(event) => updatePolicy("human_habits_capture_enabled", event.target.checked)}
                />
                Запоминать рабочие привычки
              </label>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Если выключить долгосрочную память, новые события перестанут накапливаться. Краткая выжимка после
              рабочей сессии останется доступна.
            </p>
          </div>
        ) : null}

        {memoryOverview ? (
          <MemoryOverviewPanels
            memoryOverview={memoryOverview}
            memoryActionKey={memoryActionKey}
            onPromoteNote={onPromoteMemorySnapshotToNote}
            onPromoteSkill={onPromoteMemorySnapshotToSkill}
            onArchive={onArchiveMemorySnapshot}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            {selectedMemoryServerId ? "Загрузка записей…" : "Выберите сервер, чтобы открыть настройки памяти."}
          </div>
        )}
      </div>
    </SectionCard>
  );
}
