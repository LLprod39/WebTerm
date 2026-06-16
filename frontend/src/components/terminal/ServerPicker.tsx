import { useEffect, useRef, useState } from "react";
import { Search, Server, X } from "lucide-react";

import { StatusIndicator } from "@/components/StatusIndicator";
import { Button } from "@/components/ui/button";
import type { FrontendServer } from "@/lib/api";

function formatSessionCount(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) return `${count} сессия`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} сессии`;
  return `${count} сессий`;
}

interface ServerPickerProps {
  servers: FrontendServer[];
  open: boolean;
  onClose: () => void;
  onSelect: (server: FrontendServer) => void;
  openSessionCounts: Map<number, number>;
}

export function ServerPicker({ servers, open, onClose, onSelect, openSessionCounts }: ServerPickerProps) {
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const query = search.toLowerCase().trim();
  const filtered = servers.filter((server) => {
    if (!query) return true;
    return (
      server.name.toLowerCase().includes(query) ||
      server.host.toLowerCase().includes(query) ||
      server.username.toLowerCase().includes(query) ||
      (server.group_name || "").toLowerCase().includes(query)
    );
  });

  const groups = new Map<string, FrontendServer[]>();
  for (const server of filtered) {
    const groupName = server.group_name || "Без группы";
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName)!.push(server);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="terminal-server-picker-title"
        className="relative mx-4 flex max-h-[72vh] w-full max-w-xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
              <Server className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 id="terminal-server-picker-title" className="text-base font-semibold text-foreground">
                Выбор сервера
              </h2>
              <p className="text-xs text-muted-foreground">{servers.length} серверов доступно</p>
            </div>
          </div>
          <Button
            size="icon"
            variant="ghost"
            className="text-muted-foreground hover:text-foreground"
            onClick={onClose}
            aria-label="Закрыть выбор сервера"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="border-b border-border/60 px-5 py-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={inputRef}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по имени, хосту, группе..."
              className="h-11 w-full rounded-lg border border-border bg-secondary py-2.5 pl-10 pr-11 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            {search ? (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary/80 hover:text-foreground"
                aria-label="Очистить поиск серверов"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Server className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Серверы не найдены</p>
              {search ? <p className="mt-1 text-xs text-muted-foreground/60">Попробуйте изменить запрос</p> : null}
            </div>
          ) : (
            Array.from(groups.entries()).map(([groupName, groupServers]) => (
              <div key={groupName}>
                <div className="sticky top-0 bg-secondary/40 px-5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {groupName} ({groupServers.length})
                </div>
                {groupServers.map((server) => {
                  const openSessions = openSessionCounts.get(server.id) ?? 0;
                  return (
                    <button
                      key={server.id}
                      onClick={() => {
                        onSelect(server);
                        onClose();
                      }}
                      className="flex min-h-16 w-full items-center gap-3 border-b border-border/30 px-5 py-3 text-left transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset active:bg-primary/10"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                        <Server className="h-4 w-4 text-primary" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-foreground">{server.name}</span>
                          <StatusIndicator
                            status={
                              server.status === "online"
                                ? "online"
                                : server.status === "offline"
                                  ? "offline"
                                  : "unknown"
                            }
                            showLabel={false}
                          />
                          {openSessions > 0 ? (
                            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                              {formatSessionCount(openSessions)}
                            </span>
                          ) : null}
                        </div>
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {server.username}@{server.host}:{server.port}
                        </p>
                      </div>

                      <span className="shrink-0 text-[10px] uppercase text-muted-foreground/60">
                        {server.server_type}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
