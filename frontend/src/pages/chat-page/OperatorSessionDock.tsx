import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, Terminal, X } from "lucide-react";
import { Link } from "react-router-dom";

import { XTerminal, type TerminalConnectionStatus } from "@/components/terminal/XTerminal";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import type { OperatorSessionLine, OperatorSessionState } from "./operatorSessionTypes";

type Props = {
  session: OperatorSessionState;
  onClose: () => void;
  onModeChange: (mode: "agent" | "live") => void;
  onHumanCommand: (cmd: string) => void;
};

function lineClass(line: OperatorSessionLine): string {
  if (line.source === "you") return "text-sky-300";
  if (line.kind === "err") return "text-rose-300";
  if (line.kind === "cmd") return "text-emerald-300";
  if (line.kind === "note") return "text-zinc-500";
  return "text-zinc-300";
}

/**
 * Side shell next to operator chat.
 * Opens only for real SSH (run_command / Live). Metrics never open this.
 * Layout: chat flex-1 shrinks; dock is a fixed-width dark pane.
 */
export function OperatorSessionDock({ session, onClose, onModeChange, onHumanCommand }: Props) {
  const { lang } = useI18n();
  const logRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<TerminalConnectionStatus>("connecting");
  const lineBuf = useRef("");

  const open = session.open && Boolean(session.serverId);

  useEffect(() => {
    if (!logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [session.lines.length, session.mode]);

  const liveConnected = session.mode === "live" && status === "connected";

  const statusDot = useMemo(() => {
    if (session.mode === "live") {
      if (status === "connected") return "bg-emerald-400";
      if (status === "connecting") return "bg-amber-400 animate-pulse motion-reduce:animate-none";
      if (status === "error") return "bg-rose-400";
      return "bg-zinc-500";
    }
    return session.lines.length ? "bg-violet-400" : "bg-zinc-500";
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

  if (!open || !session.serverId) return null;

  const title = session.serverName || `server #${session.serverId}`;

  return (
    <aside
      className={cn(
        "flex h-full w-[min(100%,26rem)] shrink-0 flex-col overflow-hidden",
        "border-l border-white/[0.06] bg-[#0a0b0e]",
        "animate-in slide-in-from-right-3 fade-in-0 duration-300 motion-reduce:animate-none",
      )}
      aria-label={localize(lang, "Терминал", "Terminal")}
    >
      {/* Slim chrome */}
      <header className="flex h-10 shrink-0 items-center gap-2.5 px-3">
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot)} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-medium tracking-tight text-zinc-100">{title}</div>
        </div>
        <div className="flex items-center rounded-md bg-white/[0.04] p-0.5">
          <button
            type="button"
            onClick={() => onModeChange("agent")}
            className={cn(
              "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
              session.mode === "agent" ? "bg-white/[0.1] text-zinc-100" : "text-zinc-500 hover:text-zinc-300",
            )}
          >
            {localize(lang, "Лог", "Log")}
          </button>
          <button
            type="button"
            onClick={() => onModeChange("live")}
            className={cn(
              "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
              session.mode === "live" ? "bg-white/[0.1] text-zinc-100" : "text-zinc-500 hover:text-zinc-300",
            )}
          >
            Live
          </button>
        </div>
        <Link
          to={`/servers/${session.serverId}/terminal`}
          className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200"
          title={localize(lang, "Полный терминал", "Full terminal")}
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200"
          aria-label={localize(lang, "Закрыть", "Close")}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>

      <div className="mx-3 h-px shrink-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />

      {session.mode === "agent" ? (
        <div
          ref={logRef}
          className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5 font-mono text-[11px] leading-[1.55] tracking-tight"
        >
          {session.lines.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
              <Terminal className="h-5 w-5 text-zinc-600" strokeWidth={1.5} />
              <p className="max-w-[14rem] text-[11px] leading-relaxed text-zinc-600">
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
                    <span className="select-none text-zinc-600">
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
        <div className="relative min-h-0 flex-1 bg-black">
          <div className="absolute inset-0 px-1 pb-1 pt-0.5">
            <div
              className={cn(
                "h-full overflow-hidden rounded-lg border border-white/[0.06] bg-black",
                liveConnected && "ring-1 ring-emerald-500/20",
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
    </aside>
  );
}
