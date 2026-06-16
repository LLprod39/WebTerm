import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fetchLinuxUiLogs, type FrontendServer, type LinuxUiLogsPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

const DEFAULT_LOG_PRESETS: LinuxUiLogsPayload["presets"] = [
  { key: "journal", label: "System Journal", description: "Recent lines from journalctl", available: true },
  { key: "service", label: "Service Journal", description: "Logs for a specific systemd unit", available: true },
  { key: "syslog", label: "syslog", description: "/var/log/syslog", available: true },
  { key: "messages", label: "messages", description: "/var/log/messages", available: true },
  { key: "auth", label: "auth.log", description: "/var/log/auth.log", available: true },
  { key: "nginx_error", label: "nginx error", description: "/var/log/nginx/error.log", available: true },
  { key: "nginx_access", label: "nginx access", description: "/var/log/nginx/access.log", available: true },
  { key: "apache_error", label: "apache error", description: "/var/log/apache2/error.log or /var/log/httpd/error_log", available: true },
  { key: "apache_access", label: "apache access", description: "/var/log/apache2/access.log or /var/log/httpd/access_log", available: true },
];

export function LogsWindow({
  server,
  active,
  logsEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  logsEnabled: boolean;
}) {
  const [source, setSource] = useState("journal");
  const [serviceName, setServiceName] = useState("");
  const [lines, setLines] = useState(120);

  const logsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "logs", source, serviceName.trim(), lines],
    queryFn: () =>
      fetchLinuxUiLogs(server.id, {
        source,
        service: serviceName.trim(),
        lines,
      }),
    enabled: active && (source !== "service" || Boolean(serviceName.trim())),
    staleTime: 5_000,
  });

  const presetList = logsQuery.data?.logs.presets || DEFAULT_LOG_PRESETS;
  const selectedPreset = presetList.find((item) => item.key === source) || presetList[0];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">log viewer</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Switch between journal presets and common file logs without dropping to the terminal.
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              type="number"
              min={20}
              max={240}
              value={String(lines)}
              onChange={(event) => setLines(Math.max(20, Math.min(240, Number(event.target.value) || 120)))}
              className="h-9 w-28 bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void logsQuery.refetch()}>
              <RefreshCw className={cn("h-3.5 w-3.5", logsQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
        {!logsEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            `journalctl` is unavailable, so the app will prefer file-based sources and systemctl fallbacks.
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Presets
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Right now this app covers system, service, and common web stack logs.
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {presetList.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => setSource(preset.key)}
                    className={cn(
                      "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                      source === preset.key
                        ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
                        : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{preset.label}</div>
                        <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{preset.description}</div>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
                          preset.available
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                            : "border-border/70 bg-background/94 text-muted-foreground",
                        )}
                      >
                        {preset.available ? "ready" : "missing"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-sm font-semibold text-foreground">{selectedPreset?.label || "Logs"}</h3>
                    <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                      {lines} lines
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{selectedPreset?.description}</div>
                </div>
                {source === "service" ? (
                  <Input
                    value={serviceName}
                    onChange={(event) => setServiceName(event.target.value)}
                    placeholder="nginx.service"
                    className="h-9 min-w-[16rem] bg-background/95 text-sm font-mono"
                  />
                ) : null}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden">
              {source === "service" && !serviceName.trim() ? (
                <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
                  Enter a systemd unit name like <span className="mx-1 font-mono">nginx.service</span> to load service logs.
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <pre className="whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-5 text-foreground">
                    {logsQuery.error instanceof Error
                      ? logsQuery.error.message
                      : logsQuery.isLoading
                      ? "Loading log output..."
                      : logsQuery.data?.logs.content || "No log lines available."}
                  </pre>
                </ScrollArea>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
