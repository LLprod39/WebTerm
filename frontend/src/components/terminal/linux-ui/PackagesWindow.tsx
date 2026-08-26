import { useCallback, useDeferredValue, useMemo, useState } from "react";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiPackages,
  type FrontendServer,
  type LinuxUiPackageItem,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function PackageRow({ item }: { item: LinuxUiPackageItem }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border/70 bg-background/90 px-3 py-2">
      <span className="truncate font-mono text-xs text-foreground">{item.name}</span>
      <span className="shrink-0 ml-2 text-xs text-muted-foreground font-mono">{item.version}</span>
    </div>
  );
}

export function PackagesWindow({
  server,
  active,
  packageManager,
}: {
  server: FrontendServer;
  active: boolean;
  packageManager: string;
}) {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [installPkg, setInstallPkg] = useState("");
  const [actionOutput, setActionOutput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [tab, setTab] = useState<"installed" | "updates" | "actions">("installed");

  const packagesQuery = useQuery({
    queryKey: ["linux-ui", server.id, "packages"],
    queryFn: () => fetchLinuxUiPackages(server.id),
    enabled: active && Boolean(packageManager),
    staleTime: 20_000,
  });
  const packagesPayload = packagesQuery.data?.packages;
  const installedPackages = useMemo(() => {
    const items = packagesPayload?.installed || [];
    if (!deferredSearch) return items;
    return items.filter((item) => `${item.name} ${item.version}`.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, packagesPayload?.installed]);
  const updateLines = useMemo(() => {
    const items = packagesPayload?.updates || [];
    if (!deferredSearch) return items;
    return items.filter((item) => item.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, packagesPayload?.updates]);

  const runPkgCmd = useCallback(async (cmd: string) => {
    setIsRunning(true);
    setActionOutput(`$ ${cmd}\n`);
    try {
      const { executeServerCommand } = await import("@/lib/api");
      const res = await executeServerCommand(server.id, cmd);
      setActionOutput((p) => p + [res.output?.stdout, res.output?.stderr, res.error].filter(Boolean).join("\n") + `\nExit: ${res.output?.exit_code ?? "?"}`);
      void queryClient.invalidateQueries({ queryKey: ["linux-ui", server.id, "packages"] });
    } catch (err) {
      setActionOutput((p) => p + (err instanceof Error ? err.message : localize(lang, "Ошибка", "Failed")));
    } finally { setIsRunning(false); }
  }, [lang, server.id, queryClient]);

  const installCmd = installPkg.trim() ? (
    packageManager === "apt" ? `apt-get install -y ${installPkg.trim()}` :
    packageManager === "yum" ? `yum install -y ${installPkg.trim()}` :
    packageManager === "dnf" ? `dnf install -y ${installPkg.trim()}` :
    packageManager === "pacman" ? `pacman -S --noconfirm ${installPkg.trim()}` :
    packageManager === "apk" ? `apk add ${installPkg.trim()}` : ""
  ) : "";
  const updateCmd =
    packageManager === "apt" ? "apt-get update && apt-get upgrade -y" :
    packageManager === "yum" ? "yum update -y" :
    packageManager === "dnf" ? "dnf upgrade -y" :
    packageManager === "pacman" ? "pacman -Syu --noconfirm" :
    packageManager === "apk" ? "apk update && apk upgrade" : "";

  if (!packageManager) return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{localize(lang, "Менеджер пакетов не найден.", "No package manager detected.")}</div>;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center gap-0.5 border-b border-border/60 bg-muted/30 px-2">
        {(["installed", "updates", "actions"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} className={cn("px-3 py-2 text-xs", tab === t ? "text-foreground border-b-2 border-primary" : "text-muted-foreground hover:text-foreground")}>
            {t === "installed" ? localize(lang, `Пакеты (${installedPackages.length})`, `Packages (${installedPackages.length})`) : t === "updates" ? localize(lang, "Обновления", "Updates") : localize(lang, "Установка", "Install / update")}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 py-1">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={localize(lang, "Найти...", "Filter...")} className="h-7 w-40 text-xs" />
          <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" aria-label={localize(lang, "Обновить список пакетов", "Refresh packages")} onClick={() => void packagesQuery.refetch()}>
            <RefreshCw className={cn("h-3 w-3", packagesQuery.isFetching && "animate-spin")} />
          </Button>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">
          {tab === "installed" && (
            <div className="space-y-1">
              {packagesQuery.isLoading ? <div className="py-8 text-center text-sm text-muted-foreground">{localize(lang, "Загружаем...", "Loading...")}</div>
                : installedPackages.length === 0 ? <div className="py-8 text-center text-sm text-muted-foreground">{localize(lang, "Ничего не найдено.", "No matches.")}</div>
                : installedPackages.map((item) => <PackageRow key={`${item.name}-${item.version}`} item={item} />)}
            </div>
          )}
          {tab === "updates" && (
            <pre className="whitespace-pre-wrap font-mono text-xs leading-5 text-foreground">{updateLines.length > 0 ? updateLines.join("\n") : localize(lang, "Обновлений нет.", "No updates available.")}</pre>
          )}
          {tab === "actions" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-border/70 bg-background/90 p-3">
                <div className="text-xs font-medium text-foreground mb-2">{localize(lang, "Установить пакет", "Install package")}</div>
                <div className="flex items-center gap-2">
                  <Input value={installPkg} onChange={(e) => setInstallPkg(e.target.value)} placeholder={localize(lang, "например: nginx htop", "e.g. nginx htop")} className="h-8 flex-1 text-xs font-mono"
                    onKeyDown={(e) => { if (e.key === "Enter" && installCmd) void runPkgCmd(installCmd); }} />
                  <Button type="button" size="sm" className="h-8 text-xs" disabled={!installCmd || isRunning} onClick={() => void runPkgCmd(installCmd)}>{localize(lang, "Установить", "Install")}</Button>
                </div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/90 p-3">
                <div className="text-xs font-medium text-foreground mb-2">{localize(lang, "Обновить систему", "System update")}</div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-muted px-2 py-1.5 text-xs text-muted-foreground font-mono">{updateCmd}</code>
                  <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={isRunning} onClick={() => void runPkgCmd(updateCmd)}>{localize(lang, "Обновить", "Update")}</Button>
                </div>
              </div>
              {actionOutput && (
                <div className="rounded-xl border border-border/70 bg-card p-3">
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs leading-5 text-foreground/80">{actionOutput}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
