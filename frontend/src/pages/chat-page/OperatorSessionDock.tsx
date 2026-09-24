import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, Terminal } from "lucide-react";
import { Link } from "react-router-dom";

import { XTerminal, type TerminalConnectionStatus } from "@/components/terminal/XTerminal";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { OperatorSessionLine, OperatorSessionState } from "./operatorSessionTypes";

type Props = {
  session: OperatorSessionState;
  onModeChange: (mode: "agent" | "live") => void;
  onHumanCommand: (cmd: string) => void;
};

function lineClass(line: OperatorSessionLine): string {
  if (line.source === "you") return "text-info";
  if (line.kind === "err") return "text-destructive";
  if (line.kind === "cmd") return "text-success";
  if (line.kind === "note") return "text-muted-foreground";
  return "text-foreground/85";
}

/**
 * Terminal/session content for the shared context rail (no outer aside chrome).
 * Metrics never open this — only real SSH (run_command / Live).
 */
export function OperatorSessionDock({ session, onModeChange, onHumanCommand }: Props) {
  const { lang } = useI18n();
  const logRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<TerminalConnectionStatus>("connecting");
  const lineBuf = useRef("");

  const active = session.open && Boolean(session.serverId);

  useEffect(() => {
    if (!logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [session.lines.length, session.mode]);

  const liveConnected = session.mode === "live" && status === "connected";

  const statusDot = useMemo(() => {
    if (session.mode === "live") {
      if (status === "connected") return "bg-success";
      if (status === "connecting") return "bg-warning animate-pulse motion-reduce:animate-none";
      if (status === "error") return "bg-destructive";
      return "bg-muted-foreground/50";
    }
    return session.lines.length ? "bg-ai" : "bg-muted-foreground/50";
  }, [session.mode, session.lines.length, status]);

  const interceptInput = useCallback(
    (data: string) => {
      for (const ch of data) {
        if (ch === "\r" || ch === "\n") {
          const cmd = lineBuf.current.trim();
          lineBuf.current = "";
          if (cmd) onHumanCommand(cmd);
        } else if (ch === "\u007f" || ch === "\b") {
          lineBuf.current = lineBuf.current.slice(0, -1);
        } else if (ch >= " " || ch === "\t") {
          lineBuf.current += ch;
          if (lineBuf.current.length > 4000) {
            lineBuf.current = lineBuf.current.slice(-2000);
          }
        }
      }
      return null;
    },
    [onHumanCommand],
  );

  if (!active || !session.serverId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <Terminal className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
        <p className="max-w-[14rem] text-[12px] leading-relaxed text-muted-foreground">
          {localize(
            lang,
            "Терминал откроется, когда агент выполнит команду на сервере.",
            "The terminal opens when the agent runs a command on a server.",
          )}
        </p>
      </div>
    );
  }

  const title = session.serverName || `server #${session.serverId}`;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden" aria-label={localize(lang, "Терминал", "Terminal")}>
      <header className="flex h-10 shrink-0 items-center gap-2.5 px-3">
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot)} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-medium tracking-tight text-foreground">{title}</div>
        </div>
        <div className="flex items-center rounded-sm bg-secondary p-0.5">
          <button
            type="button"
            onClick={() => onModeChange("agent")}
            className={cn(
              "rounded-sm px-2 py-0.5 text-[10px] font-medium transition-colors",
              session.mode === "agent" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {localize(lang, "Лог", "Log")}
          </button>
          <button
            type="button"
            onClick={() => onModeChange("live")}
            className={cn(
              "rounded-sm px-2 py-0.5 text-[10px] font-medium transition-colors",
              session.mode === "live" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            Live
          </button>
        </div>
        <Link
          to={`/servers/${session.serverId}/terminal`}
          className="rounded-sm p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          title={localize(lang, "Полный терминал", "Full terminal")}
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      </header>

      <div className="mx-3 h-px shrink-0 bg-border" />

      {session.mode === "agent" ? (
        <div
          ref={logRef}
          className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5 font-mono text-[11px] leading-[1.55] tracking-tight"
        >
          {session.lines.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
              <Terminal className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
              <p className="max-w-[14rem] text-[11px] leading-relaxed text-muted-foreground">
                {localize(
                  lang,
                  "Команды ИИ появятся здесь. Live — общий шелл.",
                  "AI commands appear here. Switch to Live for a shell.",
                )}
              </p>
            </div>
          ) : (
            session.lines.map((line) => (
              <div key={line.id} className={cn("mb-0.5 whitespace-pre-wrap break-words", lineClass(line))}>
                {line.kind === "cmd" ? (
                  <>
                    <span className="select-none text-muted-foreground">
                      {line.source === "you" ? "you $ " : "ai $ "}
                    </span>
                    {line.text}
                  </>
                ) : (
                  line.text
                )}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="relative min-h-0 flex-1 bg-background">
          <div className="absolute inset-0 px-1 pb-1 pt-0.5">
            <div
              className={cn(
                "h-full overflow-hidden rounded-sm border border-border bg-background",
                liveConnected && "ring-1 ring-success/25",
              )}
            >
              <XTerminal
                serverId={session.serverId}
                active
                fontSize={12}
                lineHeight={1.3}
                scrollback={3000}
                cursorStyle="bar"
                onStatusChange={setStatus}
                onInterceptInput={interceptInput}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
