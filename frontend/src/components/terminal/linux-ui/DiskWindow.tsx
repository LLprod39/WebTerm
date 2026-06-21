import { useCallback, useEffect, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Copy, FileCode2, RefreshCw } from "lucide-react";

import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fetchLinuxUiDisk, type FrontendServer, type LinuxUiDiskMount, type LinuxUiDiskPathStat } from "@/lib/api";
import { cn } from "@/lib/utils";

const EMPTY_MOUNTS: LinuxUiDiskMount[] = [];

function diskUsageClass(percent: number | null) {
  if ((percent || 0) >= 90) return "border-destructive/30 bg-destructive/10 text-destructive";
  if ((percent || 0) >= 80) return "border-amber-500/20 bg-amber-500/10 text-amber-300";
  return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
}

function DiskMountRow({
  mount,
  selected,
  onClick,
}: {
  mount: LinuxUiDiskMount;
  selected: boolean;
  onClick: () => void;
}) {
  const fill = Math.max(0, Math.min(100, mount.percent || 0));

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{mount.mount}</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{mount.filesystem}</div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", diskUsageClass(mount.percent))}>
          {mount.percent != null ? `${mount.percent.toFixed(1)}%` : "n/a"}
        </span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-background/96">
        <div
          className={cn(
            "h-2 rounded-full transition-all",
            (mount.percent || 0) >= 90 ? "bg-destructive" : (mount.percent || 0) >= 80 ? "bg-amber-400" : "bg-emerald-400",
          )}
          style={{ width: `${fill}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        {mount.used_gb != null && mount.size_gb != null ? `${mount.used_gb} / ${mount.size_gb} GB` : "Usage unavailable"}
      </div>
    </button>
  );
}

function DiskPathRow({
  item,
  label,
  selected,
  onClick,
}: {
  item: LinuxUiDiskPathStat;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10"
          : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-foreground">{item.path}</div>
          <div className="mt-1 text-xs text-muted-foreground">{label}</div>
        </div>
        <span className="shrink-0 rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
          {item.size_mb != null ? `${item.size_mb} MB` : "n/a"}
        </span>
      </div>
    </button>
  );
}

export function DiskWindow({
  server,
  active,
  diskEnabled,
  onOpenInEditor,
}: {
  server: FrontendServer;
  active: boolean;
  diskEnabled: boolean;
  onOpenInEditor?: (path: string) => void;
}) {
  const [selectedMountPath, setSelectedMountPath] = useState<string | null>(null);
  const [mountSearch, setMountSearch] = useState("");
  const [pathSearch, setPathSearch] = useState("");
  const [mountSort, setMountSort] = useState<"usage" | "name" | "size">("usage");
  const [showCriticalOnly, setShowCriticalOnly] = useState(false);
  const [detailTab, setDetailTab] = useState<"directories" | "logs" | "cleanup">("directories");
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string | null>(null);

  const diskQuery = useQuery({
    queryKey: ["linux-ui", server.id, "disk"],
    queryFn: () => fetchLinuxUiDisk(server.id),
    enabled: active,
    staleTime: 15_000,
  });

  const diskPayload = diskQuery.data?.disk;
  const mounts = diskPayload?.mounts ?? EMPTY_MOUNTS;
  const normalizedMountSearch = mountSearch.trim().toLowerCase();
  const normalizedPathSearch = pathSearch.trim().toLowerCase();
  const filteredMounts = useMemo(() => {
    const next = mounts.filter((item) => {
      if (showCriticalOnly && (item.percent || 0) < 80) return false;
      if (!normalizedMountSearch) return true;
      return `${item.mount} ${item.filesystem}`.toLowerCase().includes(normalizedMountSearch);
    });

    return [...next].sort((left, right) => {
      if (mountSort === "name") return left.mount.localeCompare(right.mount);
      if (mountSort === "size") return (right.size_gb || 0) - (left.size_gb || 0);
      return (right.percent || 0) - (left.percent || 0);
    });
  }, [mountSort, mounts, normalizedMountSearch, showCriticalOnly]);

  useEffect(() => {
    if (!filteredMounts.length) {
      if (selectedMountPath != null) setSelectedMountPath(null);
      return;
    }
    if (!filteredMounts.some((item) => item.mount === selectedMountPath)) {
      setSelectedMountPath(filteredMounts[0].mount);
    }
  }, [filteredMounts, selectedMountPath]);

  const selectedMount = useMemo(() => {
    return mounts.find((item) => item.mount === selectedMountPath) || filteredMounts[0] || mounts[0] || null;
  }, [filteredMounts, mounts, selectedMountPath]);

  const isPathInSelectedMount = useCallback((path: string) => {
    if (!selectedMount) return true;
    const mount = selectedMount.mount.replace(/\/+$/, "") || "/";
    if (mount === "/") return true;
    return path === mount || path.startsWith(`${mount}/`);
  }, [selectedMount]);

  const visibleTopDirectories = useMemo(() => {
    return (diskPayload?.top_directories || []).filter((item) => {
      if (!isPathInSelectedMount(item.path)) return false;
      if (!normalizedPathSearch) return true;
      return item.path.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.top_directories, isPathInSelectedMount, normalizedPathSearch]);

  const visibleLargeLogs = useMemo(() => {
    return (diskPayload?.large_logs || []).filter((item) => {
      if (!isPathInSelectedMount(item.path)) return false;
      if (!normalizedPathSearch) return true;
      return item.path.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.large_logs, isPathInSelectedMount, normalizedPathSearch]);

  const visibleCleanupCandidates = useMemo(() => {
    return (diskPayload?.cleanup_candidates || []).filter((item) => {
      if (!isPathInSelectedMount(item)) return false;
      if (!normalizedPathSearch) return true;
      return item.toLowerCase().includes(normalizedPathSearch);
    });
  }, [diskPayload?.cleanup_candidates, isPathInSelectedMount, normalizedPathSearch]);

  const detailItems = useMemo(() => {
    if (detailTab === "directories") {
      return visibleTopDirectories.map((item) => ({
        path: item.path,
        sizeMb: item.size_mb,
        label: "Directory footprint",
        kind: "directory" as const,
      }));
    }
    if (detailTab === "logs") {
      return visibleLargeLogs.map((item) => ({
        path: item.path,
        sizeMb: item.size_mb,
        label: "Log footprint",
        kind: "log" as const,
      }));
    }
    return visibleCleanupCandidates.map((item) => ({
      path: item,
      sizeMb: null,
      label: "Cleanup candidate",
      kind: "cleanup" as const,
    }));
  }, [detailTab, visibleCleanupCandidates, visibleLargeLogs, visibleTopDirectories]);

  useEffect(() => {
    if (!detailItems.length) {
      if (selectedArtifactPath != null) setSelectedArtifactPath(null);
      return;
    }
    if (!detailItems.some((item) => item.path === selectedArtifactPath)) {
      setSelectedArtifactPath(detailItems[0].path);
    }
  }, [detailItems, selectedArtifactPath]);

  const selectedArtifact = useMemo(() => {
    return detailItems.find((item) => item.path === selectedArtifactPath) || detailItems[0] || null;
  }, [detailItems, selectedArtifactPath]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">disk center</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Inspect mounts, spot heavy directories, and surface cleanup candidates before the host runs out of space.
            </div>
          </div>
          <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void diskQuery.refetch()}>
            <RefreshCw className={cn("h-3.5 w-3.5", diskQuery.isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
        {!diskEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Disk tooling is limited on this host. The workspace will show whatever `df`, `du`, and `find` can provide.
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label="Mounts" value={diskPayload?.summary.mounts || 0} hint="Visible filesystems" />
          <SummaryCard label="Critical" value={diskPayload?.summary.critical_mounts || 0} hint=">= 90% full" alert={(diskPayload?.summary.critical_mounts || 0) > 0} />
          <SummaryCard label="Top Dir" value={diskPayload?.summary.top_directory_mb != null ? `${diskPayload.summary.top_directory_mb} MB` : "N/A"} hint="Largest common root discovered" />
          <SummaryCard label="Cleanup" value={diskPayload?.summary.cleanup_candidates || 0} hint="Old /tmp candidates" alert={(diskPayload?.summary.cleanup_candidates || 0) > 0} />
        </div>
        <div className="mt-4 flex flex-col gap-2 xl:flex-row xl:items-center">
          <Input
            value={mountSearch}
            onChange={(event) => setMountSearch(event.target.value)}
            placeholder="Filter mounts..."
            className="h-9 min-w-[14rem] bg-background/95 text-sm"
          />
          <Input
            value={pathSearch}
            onChange={(event) => setPathSearch(event.target.value)}
            placeholder="Filter directories, logs, cleanup..."
            className="h-9 min-w-[18rem] bg-background/95 text-sm"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant={showCriticalOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowCriticalOnly((current) => !current)}>
              Critical only
            </Button>
            {([
              { value: "usage", label: "Usage" },
              { value: "size", label: "Size" },
              { value: "name", label: "Name" },
            ] as const).map((item) => (
              <Button
                key={item.value}
                type="button"
                size="sm"
                variant={mountSort === item.value ? "default" : "outline"}
                className="h-9 text-xs"
                onClick={() => setMountSort(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Mounts</div>
              <div className="mt-1 text-xs text-muted-foreground">{filteredMounts.length} of {mounts.length} filesystems visible</div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {diskQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {diskQuery.error.message}
                  </div>
                ) : null}
                {diskQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    Loading disk data...
                  </div>
                ) : null}
                {!diskQuery.isLoading && filteredMounts.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    No mounts match the current filter.
                  </div>
                ) : null}
                {filteredMounts.map((mount) => (
                  <DiskMountRow
                    key={`${mount.filesystem}-${mount.mount}`}
                    mount={mount}
                    selected={selectedMount?.mount === mount.mount}
                    onClick={() => setSelectedMountPath(mount.mount)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_auto_minmax(0,1fr)]">
            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {selectedMount ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-mono text-sm text-foreground">{selectedMount.mount}</h3>
                    <span className={cn("rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide", diskUsageClass(selectedMount.percent))}>
                      {selectedMount.percent != null ? `${selectedMount.percent.toFixed(1)}% full` : "usage unknown"}
                    </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedMount.mount)}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        Copy mount
                      </Button>
                      {onOpenInEditor && visibleLargeLogs[0] ? (
                        <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => onOpenInEditor(visibleLargeLogs[0].path)}>
                          <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
                          Open top log
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{selectedMount.filesystem}</div>
                  <div className="mt-4 h-3 rounded-full bg-background/96">
                    <div
                      className={cn(
                        "h-3 rounded-full transition-all",
                        (selectedMount.percent || 0) >= 90 ? "bg-destructive" : (selectedMount.percent || 0) >= 80 ? "bg-amber-400" : "bg-emerald-400",
                      )}
                      style={{ width: `${Math.max(0, Math.min(100, selectedMount.percent || 0))}%` }}
                    />
                  </div>
                  <div className="mt-4 grid gap-2 sm:grid-cols-3">
                    <SummaryCard label="Size" value={selectedMount.size_gb != null ? `${selectedMount.size_gb} GB` : "N/A"} hint="Total filesystem size" />
                    <SummaryCard label="Used" value={selectedMount.used_gb != null ? `${selectedMount.used_gb} GB` : "N/A"} hint="Allocated space" alert={(selectedMount.percent || 0) >= 80} />
                    <SummaryCard label="Free" value={selectedMount.available_gb != null ? `${selectedMount.available_gb} GB` : "N/A"} hint="Available capacity" />
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted-foreground">Select a mount to inspect filesystem pressure.</div>
              )}
            </div>

            <div className="rounded-3xl border border-border/70 bg-background/88 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                {([
                  { value: "directories", label: `Directories (${visibleTopDirectories.length})` },
                  { value: "logs", label: `Logs (${visibleLargeLogs.length})` },
                  { value: "cleanup", label: `Cleanup (${visibleCleanupCandidates.length})` },
                ] as const).map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    size="sm"
                    variant={detailTab === item.value ? "default" : "outline"}
                    className="h-8 text-xs"
                    onClick={() => setDetailTab(item.value)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
                <div className="border-b border-border/60 px-4 py-3">
                  <div className="text-sm font-medium text-foreground">
                    {detailTab === "directories" ? "Largest directories" : detailTab === "logs" ? "Largest logs" : "Cleanup candidates"}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {detailTab === "directories"
                      ? "Common writable roots only. This keeps the scan responsive."
                      : detailTab === "logs"
                        ? "Heavy log files are often the fastest cleanup win."
                        : "Old top-level `/tmp` entries are surfaced here first."}
                  </div>
                </div>
                <ScrollArea className="h-full">
                  <div className="space-y-2 p-3">
                    {detailItems.length > 0 ? detailItems.map((item) => (
                      item.kind === "cleanup" ? (
                        <button
                          key={item.path}
                          type="button"
                          onClick={() => setSelectedArtifactPath(item.path)}
                          className={cn(
                            "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                            selectedArtifact?.path === item.path
                              ? "border-primary/30 bg-primary/10"
                              : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
                          )}
                        >
                          <div className="font-mono text-xs text-foreground">{item.path}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{item.label}</div>
                        </button>
                      ) : (
                        <DiskPathRow
                          key={item.path}
                          item={{ path: item.path, size_mb: item.sizeMb }}
                          label={item.label}
                          selected={selectedArtifact?.path === item.path}
                          onClick={() => setSelectedArtifactPath(item.path)}
                        />
                      )
                    )) : (
                      <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                        No items match the current storage filter.
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </section>

              <section className="min-h-0 rounded-3xl border border-border/70 bg-background/88 p-4">
                {selectedArtifact ? (
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">{selectedArtifact.label}</div>
                      <div className="mt-2 break-all font-mono text-xs text-foreground">{selectedArtifact.path}</div>
                    </div>
                    <div className="grid gap-2">
                      <SummaryCard
                        label="Type"
                        value={selectedArtifact.kind}
                        hint={selectedMount ? selectedMount.mount : "Selected storage object"}
                      />
                      <SummaryCard
                        label="Size"
                        value={selectedArtifact.sizeMb != null ? `${selectedArtifact.sizeMb} MB` : "N/A"}
                        hint={selectedArtifact.kind === "cleanup" ? "Temporary candidate size unavailable" : "Reported footprint"}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Button type="button" size="sm" variant="outline" className="h-9 justify-start text-xs" onClick={() => void navigator.clipboard.writeText(selectedArtifact.path)}>
                        <Copy className="mr-2 h-3.5 w-3.5" />
                        Copy path
                      </Button>
                      {selectedArtifact.kind === "log" && onOpenInEditor ? (
                        <Button type="button" size="sm" variant="outline" className="h-9 justify-start text-xs" onClick={() => onOpenInEditor(selectedArtifact.path)}>
                          <FileCode2 className="mr-2 h-3.5 w-3.5" />
                          Open in editor
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">Select a directory, log, or cleanup candidate to inspect it.</div>
                )}
              </section>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
