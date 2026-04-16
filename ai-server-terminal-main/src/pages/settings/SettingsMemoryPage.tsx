import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  Bot,
  RefreshCw,
  ScrollText,
  Sparkles,
  Database,
  Activity,
  Clock,
  FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchFrontendBootstrap,
  fetchServerMemoryOverview,
  fetchAuthSession,
  runServerMemoryDreams,
  updateServerMemoryPolicy,
  promoteServerMemorySnapshotToNote,
  promoteServerMemorySnapshotToSkill,
  archiveServerMemorySnapshot,
  type FrontendServer,
  type ServerMemoryOverviewResponse,
  type ServerMemorySnapshotRecord,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { QueryStateBlock } from "@/components/ui/page-shell";

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsMemoryPage() {
  const queryClient = useQueryClient();

  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  const { data: frontendBootstrap } = useQuery({
    queryKey: ["settings", "memory", "servers"],
    queryFn: fetchFrontendBootstrap,
    enabled: isAdmin,
    staleTime: 60_000,
  });

  const memoryServers = frontendBootstrap?.servers || [];
  const [selectedMemoryServerId, setSelectedMemoryServerId] = useState<number | null>(null);
  const [memoryDreamRunning, setMemoryDreamRunning] = useState(false);
  const [memoryPolicySaving, setMemoryPolicySaving] = useState(false);
  const [memoryActionKey, setMemoryActionKey] = useState<string | null>(null);
  const [memoryPolicyDraft, setMemoryPolicyDraft] = useState<ServerMemoryOverviewResponse["policy"] | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    if (selectedMemoryServerId) return;
    const firstServer = memoryServers[0];
    if (firstServer) {
      setSelectedMemoryServerId(firstServer.id);
    }
  }, [isAdmin, memoryServers, selectedMemoryServerId]);

  const {
    data: memoryOverview,
    isLoading: memoryLoading,
    refetch: refetchMemoryOverview,
  } = useQuery({
    queryKey: ["settings", "memory", "overview", selectedMemoryServerId],
    queryFn: () => fetchServerMemoryOverview(selectedMemoryServerId as number),
    enabled: isAdmin && Boolean(selectedMemoryServerId),
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!memoryOverview) return;
    setMemoryPolicyDraft(memoryOverview.policy);
  }, [memoryOverview]);

  const selectedMemoryServer = useMemo(
    () => memoryServers.find((server) => server.id === selectedMemoryServerId) || null,
    [memoryServers, selectedMemoryServerId],
  );

  const refreshMemoryOverview = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    await queryClient.invalidateQueries({ queryKey: ["settings", "memory", "overview", selectedMemoryServerId] });
    await refetchMemoryOverview();
  }, [queryClient, refetchMemoryOverview, selectedMemoryServerId]);

  const onRunMemoryDreams = useCallback(async () => {
    if (!selectedMemoryServerId) return;
    setMemoryDreamRunning(true);
    try {
      await runServerMemoryDreams(selectedMemoryServerId, { job_kind: "hybrid" });
      await refreshMemoryOverview();
    } finally {
      setMemoryDreamRunning(false);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onSaveMemoryPolicy = useCallback(async () => {
    if (!selectedMemoryServerId || !memoryPolicyDraft) return;
    setMemoryPolicySaving(true);
    try {
      await updateServerMemoryPolicy(selectedMemoryServerId, memoryPolicyDraft);
      await refreshMemoryOverview();
    } finally {
      setMemoryPolicySaving(false);
    }
  }, [memoryPolicyDraft, refreshMemoryOverview, selectedMemoryServerId]);

  const onArchiveMemorySnapshot = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`archive:${snapshotId}`);
    try {
      await archiveServerMemorySnapshot(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToNote = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`note:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToNote(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const onPromoteMemorySnapshotToSkill = useCallback(async (snapshotId: number) => {
    if (!selectedMemoryServerId) return;
    setMemoryActionKey(`skill:${snapshotId}`);
    try {
      await promoteServerMemorySnapshotToSkill(selectedMemoryServerId, snapshotId);
      await refreshMemoryOverview();
    } finally {
      setMemoryActionKey(null);
    }
  }, [refreshMemoryOverview, selectedMemoryServerId]);

  const renderMemorySnapshotAudit = useCallback((item: ServerMemorySnapshotRecord) => (
    <div className="mt-3 space-y-2 text-[10px] text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-secondary px-1.5 py-0.5">{item.source_kind}</span>
        {item.source_ref ? <span className="rounded bg-secondary/60 px-1.5 py-0.5">{item.source_ref}</span> : null}
        <span>confidence {Math.round((item.confidence || 0) * 100)}%</span>
        <span>importance {item.importance_score}</span>
        <span>stability {item.stability_score}</span>
        {item.created_by_username ? <span>by {item.created_by_username}</span> : null}
        {item.updated_at ? <span>{new Date(item.updated_at).toLocaleString()}</span> : null}
      </div>
      {item.action_summary ? <p className="text-[11px] text-foreground/80">{item.action_summary}</p> : null}
      {item.rewrite_reason ? <p>Reason: {item.rewrite_reason}</p> : null}
      {item.prior_version ? <p>Prior version: v{item.prior_version}</p> : null}
      {item.history.length > 1 ? (
        <details className="rounded-md border border-border/60 bg-background/30 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium text-foreground">
            Version history ({item.history.length})
          </summary>
          <div className="mt-2 space-y-2">
            {item.history.map((historyItem) => (
              <div key={historyItem.id} className="rounded border border-border/50 bg-secondary/10 px-2 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={historyItem.is_active ? "secondary" : "outline"}>v{historyItem.version}</Badge>
                  {historyItem.source_kind ? <span>{historyItem.source_kind}</span> : null}
                  {historyItem.source_ref ? <span>{historyItem.source_ref}</span> : null}
                  {historyItem.created_by_username ? <span>by {historyItem.created_by_username}</span> : null}
                  {historyItem.updated_at ? <span>{new Date(historyItem.updated_at).toLocaleString()}</span> : null}
                </div>
                {historyItem.action_summary ? <p className="mt-1 text-[11px] text-foreground/80">{historyItem.action_summary}</p> : null}
                {historyItem.rewrite_reason ? <p className="mt-1">Reason: {historyItem.rewrite_reason}</p> : null}
                {historyItem.content_preview ? (
                  <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed">{historyItem.content_preview}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  ), []);

  const renderWorkerStateCard = useCallback((label: string, state: ServerMemoryOverviewResponse["daemon_state"] | undefined) => {
    if (!state) return null;
    const statusTone =
      state.status === "running"
        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
        : state.status === "error"
          ? "bg-destructive/10 text-destructive border-destructive/30"
          : "bg-secondary text-muted-foreground border-border";
    return (
      <div key={`${label}-${state.worker_key}`} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <span className={cn("rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide", statusTone)}>
            {state.status}
          </span>
          {state.is_stale ? <Badge variant="destructive">stale</Badge> : null}
        </div>
        <div className="mt-2 space-y-1 text-xs text-muted-foreground">
          {state.command ? <p className="truncate">cmd: {state.command}</p> : null}
          <p>worker: {state.worker_key}</p>
          {state.hostname ? <p>host: {state.hostname}</p> : null}
          {state.pid ? <p>pid: {state.pid}</p> : null}
          {state.heartbeat_at ? <p>heartbeat: {new Date(state.heartbeat_at).toLocaleString()}</p> : null}
          {state.last_cycle_finished_at ? <p>last cycle: {new Date(state.last_cycle_finished_at).toLocaleString()}</p> : null}
          {state.last_error ? <p className="text-destructive">error: {state.last_error}</p> : null}
          {Object.keys(state.last_summary || {}).length ? (
            <details className="rounded border border-border/50 bg-background/30 px-2 py-2">
              <summary className="cursor-pointer text-[11px] font-medium text-foreground">Last summary</summary>
              <pre className="mt-2 whitespace-pre-wrap text-[10px] leading-relaxed text-muted-foreground">
                {JSON.stringify(state.last_summary, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
    );
  }, []);

  const renderMemoryCandidateActions = useCallback((item: ServerMemorySnapshotRecord) => (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-3 text-xs"
        disabled={memoryActionKey === `note:${item.id}`}
        onClick={() => void onPromoteMemorySnapshotToNote(item.id)}
      >
        {memoryActionKey === `note:${item.id}` ? "Promoting..." : "Promote Note"}
      </Button>
      {item.memory_key.startsWith("skill_draft:") ? (
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          disabled={memoryActionKey === `skill:${item.id}`}
          onClick={() => void onPromoteMemorySnapshotToSkill(item.id)}
        >
          {memoryActionKey === `skill:${item.id}` ? "Promoting..." : "Promote Skill"}
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        className="h-7 border-destructive/30 px-3 text-xs text-destructive hover:bg-destructive/10"
        disabled={memoryActionKey === `archive:${item.id}`}
        onClick={() => void onArchiveMemorySnapshot(item.id)}
      >
        {memoryActionKey === `archive:${item.id}` ? "Archiving..." : "Archive"}
      </Button>
    </div>
  ), [memoryActionKey, onArchiveMemorySnapshot, onPromoteMemorySnapshotToNote, onPromoteMemorySnapshotToSkill]);

  if (authLoading) {
    return <QueryStateBlock loading>{null}</QueryStateBlock>;
  }

  if (!isAdmin) {
    return <Navigate to="/settings/ai" replace />;
  }

  return (
    <div className="space-y-6 pb-10">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">AI Memory</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">Долговременная память, snapshots и паттерны агентов</p>
      </div>

      {/* Main Memory Section */}
      <SectionCard
        title="AI Memory и Dreams"
        icon={ScrollText}
        description="Настройка снов, canonical snapshots и learned operational patterns"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5"
              onClick={() => void refreshMemoryOverview()}
              disabled={!selectedMemoryServerId || memoryLoading}
            >
              <RefreshCw className={cn("h-3 w-3", memoryLoading && "animate-spin")} />
              Обновить
            </Button>
            <Button
              size="sm"
              className="h-7 gap-1.5"
              onClick={() => void onRunMemoryDreams()}
              disabled={!selectedMemoryServerId || memoryDreamRunning}
            >
              <Sparkles className={cn("h-3 w-3", memoryDreamRunning && "animate-spin")} />
              {memoryDreamRunning ? "Dreaming..." : "Run Dreams Now"}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {/* Server Selection */}
          <div className="grid gap-3 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
            <div className="space-y-1.5">
              <Label className="text-xs">Сервер</Label>
              <Select
                value={selectedMemoryServerId ? String(selectedMemoryServerId) : ""}
                onValueChange={(value) => setSelectedMemoryServerId(Number(value))}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Выбери сервер" />
                </SelectTrigger>
                <SelectContent>
                  {memoryServers.map((server: FrontendServer) => (
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
                  Dreams daemon: {memoryOverview?.daemon_state?.status || "unknown"}
                </Badge>
                {memoryOverview?.daemon_state?.is_stale ? (
                  <Badge variant="destructive">stale heartbeat</Badge>
                ) : null}
              </div>
            </div>
          </div>

          {/* Policy Controls */}
          {memoryPolicyDraft ? (
            <div className="space-y-4 rounded-xl border border-border bg-secondary/10 px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-foreground">Dream Policy</p>
                <Button size="sm" variant="outline" className="h-7" onClick={onSaveMemoryPolicy} disabled={memoryPolicySaving}>
                  {memoryPolicySaving ? "Сохранение..." : "Сохранить"}
                </Button>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-3 transition-colors hover:bg-secondary/30">
                  <div>
                    <p className="text-xs font-medium">AI Memory</p>
                    <p className="text-[10px] text-muted-foreground">Включить систему памяти</p>
                  </div>
                  <Switch
                    checked={memoryPolicyDraft.ai_memory_enabled}
                    onCheckedChange={(v) => setMemoryPolicyDraft((d) => d ? { ...d, ai_memory_enabled: v } : null)}
                  />
                </label>

                <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-3 transition-colors hover:bg-secondary/30">
                  <div>
                    <p className="text-xs font-medium">Операционная память</p>
                    <p className="text-[10px] text-muted-foreground">Оперативный контекст</p>
                  </div>
                  <Switch
                    checked={memoryPolicyDraft.operational_memory_enabled}
                    onCheckedChange={(v) => setMemoryPolicyDraft((d) => d ? { ...d, operational_memory_enabled: v } : null)}
                  />
                </label>

                <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-3 transition-colors hover:bg-secondary/30">
                  <div>
                    <p className="text-xs font-medium">RDP семантика</p>
                    <p className="text-[10px] text-muted-foreground">RDP semantic capture</p>
                  </div>
                  <Switch
                    checked={memoryPolicyDraft.rdp_semantic_enabled}
                    onCheckedChange={(v) => setMemoryPolicyDraft((d) => d ? { ...d, rdp_semantic_enabled: v } : null)}
                  />
                </label>
              </div>
            </div>
          ) : null}

          {/* Memory Stats */}
          {memoryOverview ? (
            <>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
                {[
                  { label: "Canonical", value: memoryOverview.stats.canonical },
                  { label: "Patterns", value: memoryOverview.stats.patterns },
                  { label: "Automation", value: memoryOverview.stats.automation_candidates },
                  { label: "Skill Drafts", value: memoryOverview.stats.skill_drafts },
                  { label: "Revalidation", value: memoryOverview.stats.revalidation_open },
                  { label: "Episodes", value: memoryOverview.stats.episodes },
                  { label: "Archive", value: memoryOverview.stats.archive },
                ].map((stat) => (
                  <div key={stat.label} className="group/stat relative overflow-hidden rounded-xl border border-primary/5 bg-background/50 px-4 py-4 shadow-sm transition-all hover:border-primary/20 hover:bg-background/80 hover:shadow-md">
                    <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 transition-opacity group-hover/stat:opacity-100" />
                    <p className="relative z-10 text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70 group-hover/stat:text-primary transition-colors">{stat.label}</p>
                    <p className="relative z-10 mt-2 text-2xl font-black text-foreground/90">{stat.value}</p>
                  </div>
                ))}
              </div>

              {/* Workers Status */}
              <SectionCard title="Worker status" icon={Activity} description="Состояние фоновых workers">
                <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
                  {renderWorkerStateCard("Memory dreams", memoryOverview.worker_states?.memory_dreams || memoryOverview.daemon_state)}
                  {renderWorkerStateCard("Agent execution", memoryOverview.worker_states?.agent_execution)}
                  {renderWorkerStateCard("Watchers", memoryOverview.worker_states?.watchers)}
                </div>
              </SectionCard>

              {/* Canonical Snapshots */}
              {memoryOverview.canonical.length > 0 ? (
                <SectionCard title="Canonical snapshots" icon={Database} description="Активная память сервера">
                  <div className="space-y-2">
                    {memoryOverview.canonical.map((item) => (
                      <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{item.title}</p>
                          <Badge variant="secondary">{item.memory_key}</Badge>
                          <Badge variant="outline">v{item.version}</Badge>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
                        {renderMemorySnapshotAudit(item)}
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}

              {/* Learned Candidates */}
              {memoryOverview.patterns.length > 0 || memoryOverview.automation_candidates.length > 0 || memoryOverview.skill_drafts.length > 0 ? (
                <SectionCard title="Learned candidates" icon={Bot} description="Предложения для operational knowledge">
                  <div className="space-y-3">
                    {[...memoryOverview.patterns, ...memoryOverview.automation_candidates, ...memoryOverview.skill_drafts].map((item) => (
                      <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{item.title}</p>
                          <Badge variant="secondary">{item.memory_key}</Badge>
                          <Badge variant="outline">v{item.version}</Badge>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.content}</p>
                        {renderMemorySnapshotAudit(item)}
                        {renderMemoryCandidateActions(item)}
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}

              {/* Revalidation Queue */}
              {memoryOverview.revalidation.length > 0 ? (
                <SectionCard title="Revalidation queue" icon={RefreshCw} description="Факты для перепроверки">
                  <div className="space-y-2">
                    {memoryOverview.revalidation.map((item) => (
                      <div key={item.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{item.title}</p>
                          <Badge variant="outline">{item.memory_key}</Badge>
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}

              {/* Recent Episodes */}
              {memoryOverview.episodes.length > 0 ? (
                <SectionCard title="Recent episodes" icon={Clock} description="Последние схлопнутые эпизоды">
                  <div className="space-y-2">
                    {memoryOverview.episodes.slice(0, 6).map((item) => (
                      <div key={item.id} className="rounded-lg border border-border bg-secondary/10 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{item.title}</p>
                          <Badge variant="secondary">{item.episode_kind}</Badge>
                          <Badge variant="outline">{item.event_count} events</Badge>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{item.summary}</p>
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}

              {/* Archive */}
              {memoryOverview.archive.length > 0 ? (
                <SectionCard title="Archive" icon={FolderOpen} description="Старые и superseded artefacts">
                  <div className="space-y-2">
                    {memoryOverview.archive.slice(0, 6).map((item) => (
                      <div key={`${item.kind}-${item.id}`} className="rounded-lg border border-border/60 bg-secondary/5 px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{item.title}</p>
                          <Badge variant="outline">{item.kind}</Badge>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                          {"content" in item ? item.content : item.summary}
                        </p>
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}
            </>
          ) : (
            <QueryStateBlock loading={!!(selectedMemoryServerId && memoryLoading)}>
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                Выбери сервер, чтобы увидеть AI memory.
              </div>
            </QueryStateBlock>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
