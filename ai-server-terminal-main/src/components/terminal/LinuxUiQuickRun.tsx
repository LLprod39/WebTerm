import { useCallback, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Clock,
  Copy,
  ListFilter,
  Loader2,
  Play,
  RotateCcw,
  Search,
  Terminal,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { executeServerCommand, type FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

interface CommandResult {
  id: number;
  command: string;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  timestamp: Date;
  duration: number;
  error?: string;
}

let cmdSeq = 0;

export function QuickRunWindow({
  server,
  active,
}: {
  server: FrontendServer;
  active: boolean;
}) {
  const { toast } = useToast();
  const [command, setCommand] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [history, setHistory] = useState<CommandResult[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [historyFilter, setHistoryFilter] = useState("");
  const [showOnlyFailures, setShowOnlyFailures] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const runCommand = useCallback(
    async (cmd: string) => {
      if (!cmd.trim() || isRunning) return;

      setIsRunning(true);
      const start = Date.now();
      const id = ++cmdSeq;

      try {
        const res = await executeServerCommand(server.id, cmd.trim());
        const duration = Date.now() - start;

        const result: CommandResult = {
          id,
          command: cmd.trim(),
          stdout: res.output?.stdout || "",
          stderr: res.output?.stderr || "",
          exitCode: res.output?.exit_code ?? null,
          timestamp: new Date(),
          duration,
          error: res.error || undefined,
        };

        setHistory((prev) => [...prev, result]);
        setCommand("");
        setHistoryIndex(-1);
      } catch (err) {
        setHistory((prev) => [
          ...prev,
          {
            id,
            command: cmd.trim(),
            stdout: "",
            stderr: "",
            exitCode: null,
            timestamp: new Date(),
            duration: Date.now() - start,
            error: err instanceof Error ? err.message : "Command execution failed",
          },
        ]);
      } finally {
        setIsRunning(false);
        setTimeout(() => {
          scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
        }, 50);
      }
    },
    [server.id, isRunning],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && command.trim()) {
        e.preventDefault();
        void runCommand(command);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const cmds = history.map((h) => h.command);
        if (cmds.length === 0) return;
        const next = historyIndex < 0 ? cmds.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(next);
        setCommand(cmds[next]);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const cmds = history.map((h) => h.command);
        if (historyIndex < 0) return;
        const next = historyIndex + 1;
        if (next >= cmds.length) {
          setHistoryIndex(-1);
          setCommand("");
        } else {
          setHistoryIndex(next);
          setCommand(cmds[next]);
        }
      }
    },
    [command, history, historyIndex, runCommand],
  );

  const copyOutput = useCallback((text: string) => {
    void navigator.clipboard.writeText(text);
    toast({ title: "Copied", description: "Output copied to clipboard" });
  }, [toast]);

  const copyCommand = useCallback((text: string) => {
    void navigator.clipboard.writeText(text);
    toast({ title: "Copied", description: "Command copied to clipboard" });
  }, [toast]);

  const quickCommands = [
    { label: "uptime", cmd: "uptime" },
    { label: "whoami", cmd: "whoami" },
    { label: "df -h", cmd: "df -h" },
    { label: "free -m", cmd: "free -m" },
    { label: "ip addr", cmd: "ip addr show" },
    { label: "last -5", cmd: "last -5" },
    { label: "cat /etc/os-release", cmd: "cat /etc/os-release" },
    { label: "systemctl --failed", cmd: "systemctl --failed" },
  ];

  const filteredHistory = useMemo(() => {
    const query = historyFilter.trim().toLowerCase();
    return history.filter((item) => {
      if (showOnlyFailures && !item.error && item.exitCode === 0) return false;
      if (!query) return true;
      return `${item.command}\n${item.stdout}\n${item.stderr}\n${item.error || ""}`.toLowerCase().includes(query);
    });
  }, [history, historyFilter, showOnlyFailures]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card text-foreground">
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">Quick Run</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Run a focused command, inspect the result, and re-run from history when needed.
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded-xl border border-border bg-background px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">History</div>
              <div className="mt-1 text-base font-semibold text-foreground">{history.length}</div>
            </div>
            <div className="rounded-xl border border-border bg-background px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Failures</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {history.filter((item) => item.error || item.exitCode !== 0).length}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-background px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Host</div>
              <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{server.host}</div>
            </div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Terminal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Quick presets</span>
          <div className="flex flex-wrap gap-1.5">
            {quickCommands.map((qc) => (
              <button
                key={qc.cmd}
                type="button"
                onClick={() => void runCommand(qc.cmd)}
                disabled={isRunning}
                className="rounded-full border border-border bg-background px-2.5 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:border-primary/20 hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                {qc.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="border-b border-border bg-secondary/20 px-4 py-2.5">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={historyFilter}
              onChange={(event) => setHistoryFilter(event.target.value)}
              placeholder="Filter command history and output..."
              className="h-9 rounded-xl border-border bg-background pl-9 text-sm text-foreground placeholder:text-muted-foreground"
            />
          </div>
          <Button
            type="button"
            size="sm"
            variant={showOnlyFailures ? "default" : "outline"}
            className="h-9 rounded-xl border-border px-3 text-xs"
            onClick={() => setShowOnlyFailures((value) => !value)}
          >
            <ListFilter className="mr-1.5 h-3.5 w-3.5" />
            Failed only
          </Button>
          {history.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 rounded-xl border-border bg-background px-3 text-xs text-foreground hover:bg-secondary"
              onClick={() => setHistory([])}
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Clear history
            </Button>
          ) : null}
        </div>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto bg-transparent">
        {history.length === 0 ? (
          <div className="flex h-full items-center justify-center p-6">
            <div className="text-center">
              <Terminal className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Run commands on {server.name}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Use quick presets for inspection or type your own command below.
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3 px-4 py-4">
            {filteredHistory.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                No command history items match the current filter.
              </div>
            ) : null}
            {filteredHistory.map((result) => (
              <div key={result.id} className="rounded-[1.2rem] border border-border bg-background/70 p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 font-mono text-xs text-primary">$</span>
                    <span className="break-all font-mono text-xs text-foreground">{result.command}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span
                      className={cn(
                        "rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-wide",
                        result.error
                          ? "border-destructive/30 bg-destructive/10 text-destructive"
                          : result.exitCode === 0
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                            : result.exitCode != null
                            ? "border-border bg-secondary text-muted-foreground"
                              : "border-border bg-secondary/50 text-muted-foreground",
                      )}
                    >
                      {result.error ? "err" : result.exitCode != null ? `exit ${result.exitCode}` : "?"}
                    </span>
                    <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                      <Clock className="h-2.5 w-2.5" />
                      {result.duration}ms
                    </span>
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{result.timestamp.toLocaleTimeString()}</span>
                  <span>•</span>
                  <span>{result.stdout ? `${result.stdout.split("\n").length} stdout lines` : "no stdout"}</span>
                  <span>•</span>
                  <span>{result.stderr ? `${result.stderr.split("\n").length} stderr lines` : "no stderr"}</span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 rounded-xl border-border bg-background text-[11px] text-foreground hover:bg-secondary"
                    onClick={() => void runCommand(result.command)}
                    disabled={isRunning}
                  >
                    <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                    Run again
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 rounded-xl border-border bg-background text-[11px] text-foreground hover:bg-secondary"
                    onClick={() => copyCommand(result.command)}
                  >
                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                    Copy command
                  </Button>
                  {result.stdout ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 rounded-xl border-border bg-background text-[11px] text-foreground hover:bg-secondary"
                      onClick={() => copyOutput(result.stdout)}
                    >
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      Copy stdout
                    </Button>
                  ) : null}
                </div>

                {result.error ? (
                  <div className="mt-3 flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/8 p-3">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-destructive" />
                    <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-destructive">
                      {result.error}
                    </pre>
                  </div>
                ) : null}

                {result.stdout ? (
                  <div className="group relative mt-3 rounded-xl border border-border bg-card p-3">
                    <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground">
                      {result.stdout}
                    </pre>
                    <span className="pointer-events-none absolute right-2 top-2 rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                      stdout
                    </span>
                  </div>
                ) : null}

                {result.stderr ? (
                  <div className="mt-2 rounded-xl border border-border bg-secondary/50 p-3">
                    <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-muted-foreground">
                      {result.stderr}
                    </pre>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-border bg-secondary/20 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="shrink-0 font-mono text-xs text-primary">
            {server.username}@{server.host}:$
          </span>
          <Input
            ref={inputRef}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command..."
            className="h-9 flex-1 rounded-xl border-border bg-background px-3 font-mono text-xs text-foreground placeholder:text-muted-foreground shadow-none"
            disabled={isRunning}
            autoFocus
          />
          {isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 rounded-xl border-border bg-background px-3 text-foreground hover:bg-secondary"
              disabled={!command.trim()}
              onClick={() => void runCommand(command)}
            >
              <Play className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
