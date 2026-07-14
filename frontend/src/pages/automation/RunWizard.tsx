import { useEffect, useMemo, useState } from "react";
import { Layers, Play, Server, Shield } from "lucide-react";
import type { FrontendGroup, FrontendServer } from "@/lib/api";
import { previewPlaybookInventory } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { resolveServerOs } from "@/lib/server-os";
import { cn } from "@/lib/utils";

interface RunWizardProps {
  lang: string;
  playbookName: string;
  servers: FrontendServer[];
  groups: FrontendGroup[];
  running: boolean;
  onBack: () => void;
  onConfirm: (opts: {
    server_ids: number[];
    group_ids: number[];
    concurrency: number;
    dry_run: boolean;
    become: boolean;
  }) => void;
  ansibleAvailable?: boolean;
}

export function RunWizard({
  lang,
  playbookName,
  servers,
  groups,
  running,
  onBack,
  onConfirm,
  ansibleAvailable = false,
}: RunWizardProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [serverIds, setServerIds] = useState<Set<number>>(new Set());
  const [groupIds, setGroupIds] = useState<Set<number>>(new Set());
  const [concurrency, setConcurrency] = useState(4);
  const [dryRun, setDryRun] = useState(false);
  const [become, setBecome] = useState(true);
  const [inventory, setInventory] = useState("");
  const [resolvedCount, setResolvedCount] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);

  const onlineIds = useMemo(
    () => new Set(servers.filter((s) => s.status === "online").map((s) => s.id)),
    [servers],
  );

  const toggleServer = (id: number) => {
    setServerIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (id: number) => {
    setGroupIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  useEffect(() => {
    if (step !== 3) return;
    let cancelled = false;
    setPreviewLoading(true);
    void previewPlaybookInventory({
      server_ids: Array.from(serverIds),
      group_ids: Array.from(groupIds),
    })
      .then((res) => {
        if (cancelled) return;
        setInventory(res.inventory || "");
        setResolvedCount(res.count || 0);
      })
      .catch(() => {
        if (cancelled) return;
        setInventory("");
        setResolvedCount(0);
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [step, serverIds, groupIds]);

  const hasTargets = serverIds.size > 0 || groupIds.size > 0;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("Назад", "Back")}
          </button>
          <h2 className="mt-1 font-display text-lg font-semibold text-foreground">
            {tr("Запуск", "Run")}: {playbookName}
          </h2>
        </div>
        <div className="flex items-center gap-1.5">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className={cn(
                "flex h-8 min-w-8 items-center justify-center rounded-sm border px-2 text-2xs font-mono uppercase tracking-wider",
                step === n
                  ? "border-primary bg-primary text-primary-foreground"
                  : step > n
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border bg-card text-muted-foreground",
              )}
            >
              {n === 1 ? tr("Цели", "Targets") : n === 2 ? tr("Опции", "Options") : tr("OK", "OK")}
            </div>
          ))}
        </div>
      </div>

      {step === 1 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Server className="h-4 w-4 text-primary" />
                {tr("Серверы", "Servers")} ({serverIds.size})
              </h3>
              <div className="flex gap-1">
                <Button
                  size="xs"
                  variant="outline"
                  className="h-7"
                  onClick={() => setServerIds(new Set(onlineIds))}
                >
                  {tr("Онлайн", "Online")}
                </Button>
                <Button size="xs" variant="outline" className="h-7" onClick={() => setServerIds(new Set())}>
                  {tr("Сброс", "Clear")}
                </Button>
              </div>
            </div>
            <div className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
              {servers.map((server) => (
                <button
                  key={server.id}
                  type="button"
                  onClick={() => toggleServer(server.id)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-sm border px-3 py-2.5 text-left text-xs transition-colors",
                    serverIds.has(server.id)
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border bg-surface-0/50 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <ServerOsBadge kind={resolveServerOs(server)} size="sm" />
                  <StatusIndicator status={server.status} showLabel={false} />
                  <span className="min-w-0 flex-1 truncate font-medium">{server.name}</span>
                  <span className="font-mono opacity-60">{server.host}</span>
                </button>
              ))}
              {servers.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">{tr("Нет серверов", "No servers")}</p>
              ) : null}
            </div>
          </div>

          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Layers className="h-4 w-4 text-primary" />
              {tr("Группы", "Groups")} ({groupIds.size})
            </h3>
            <div className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
              {groups.map((group) => (
                <button
                  key={group.id}
                  type="button"
                  onClick={() => toggleGroup(group.id)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-sm border px-3 py-2.5 text-left text-xs transition-colors",
                    groupIds.has(group.id)
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border bg-surface-0/50 text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: group.color || "hsl(var(--primary))" }}
                  />
                  <span className="min-w-0 flex-1 truncate font-medium">{group.name}</span>
                  <span className="font-mono opacity-60">{group.server_count ?? "—"}</span>
                </button>
              ))}
              {groups.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">{tr("Нет групп", "No groups")}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="rounded-sm border border-border bg-card p-5 shadow-elev-1 space-y-5 max-w-xl">
          {!ansibleAvailable ? (
            <div className="rounded-sm border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground">
              {tr(
                "Ansible не найден на backend — установите ansible-core или Docker, чтобы запускать playbook.",
                "Ansible not found on backend — install ansible-core or Docker to run playbooks.",
              )}
            </div>
          ) : null}
          <div className="space-y-2">
            <Label className="text-2xs uppercase tracking-wider text-muted-foreground">
              {tr("Параллельность (forks)", "Concurrency (forks)")}
            </Label>
            <input
              type="range"
              min={1}
              max={12}
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
              className="w-full accent-[hsl(var(--primary))]"
            />
            <p className="font-mono text-sm text-foreground">{concurrency}</p>
          </div>
          <label className="flex cursor-pointer items-start gap-3 rounded-sm border border-border bg-surface-0 p-3">
            <input type="checkbox" checked={become} onChange={(e) => setBecome(e.target.checked)} className="mt-1" />
            <div>
              <div className="text-sm font-medium text-foreground">become (sudo)</div>
              <p className="mt-1 text-xs text-muted-foreground">
                {tr("Запускать задачи с привилегиями (ansible --become).", "Run with elevated privileges (ansible --become).")}
              </p>
            </div>
          </label>
          <label className="flex cursor-pointer items-start gap-3 rounded-sm border border-border bg-surface-0 p-3">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="mt-1" />
            <div>
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Shield className="h-4 w-4 text-primary" />
                {tr("Check mode / dry-run", "Check mode / dry-run")}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {tr(
                  "ansible-playbook --check --diff: показывает изменения, ничего не меняя.",
                  "ansible-playbook --check --diff: shows changes without applying them.",
                )}
              </p>
            </div>
          </label>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-3">
            <h3 className="text-sm font-medium text-foreground">{tr("Подтверждение", "Confirm")}</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">{tr("Playbook", "Playbook")}</dt>
                <dd className="font-medium text-foreground">{playbookName}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">{tr("Серверы / группы", "Servers / groups")}</dt>
                <dd className="font-mono text-foreground">
                  {serverIds.size} / {groupIds.size}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">{tr("Хостов после resolve", "Resolved hosts")}</dt>
                <dd className="font-mono text-foreground">{previewLoading ? "…" : resolvedCount}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">{tr("Параллельность (forks)", "Forks")}</dt>
                <dd className="font-mono text-foreground">{concurrency}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
                <dt className="text-muted-foreground">become</dt>
                <dd className="font-mono text-foreground">{become ? "yes" : "no"}</dd>
              </div>
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-muted-foreground">Check / dry-run</dt>
                <dd className="font-mono text-foreground">{dryRun ? "yes" : "no"}</dd>
              </div>
            </dl>
          </div>
          <div className="rounded-sm border border-border bg-card p-4 shadow-elev-1 space-y-2">
            <h3 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
              Inventory preview
            </h3>
            <pre className="max-h-64 overflow-auto rounded-sm border border-border bg-surface-0 p-3 font-mono text-2xs text-muted-foreground whitespace-pre-wrap">
              {previewLoading ? tr("Загрузка…", "Loading…") : inventory || tr("Пусто", "Empty")}
            </pre>
          </div>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-9"
          disabled={step === 1 || running}
          onClick={() => setStep((s) => (s > 1 ? ((s - 1) as 1 | 2 | 3) : s))}
        >
          {tr("Назад", "Back")}
        </Button>
        {step < 3 ? (
          <Button
            size="sm"
            className="h-9 shadow-elev-1"
            disabled={step === 1 && !hasTargets}
            onClick={() => setStep((s) => (s < 3 ? ((s + 1) as 1 | 2 | 3) : s))}
          >
            {tr("Далее", "Next")}
          </Button>
        ) : (
          <Button
            size="sm"
            className="h-9 gap-1.5 px-5 shadow-elev-1"
            disabled={running || resolvedCount === 0 || !ansibleAvailable}
            onClick={() =>
              onConfirm({
                server_ids: Array.from(serverIds),
                group_ids: Array.from(groupIds),
                concurrency,
                dry_run: dryRun,
                become,
              })
            }
          >
            <Play className="h-3.5 w-3.5" />
            {running
              ? tr("Запуск…", "Starting…")
              : dryRun
                ? tr("Dry-run", "Dry-run")
                : tr(`Запустить на ${resolvedCount || "…"}`, `Run on ${resolvedCount || "…"}`)}
          </Button>
        )}
      </div>
    </section>
  );
}
