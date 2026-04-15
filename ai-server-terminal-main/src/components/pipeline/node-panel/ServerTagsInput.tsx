import { Plus, X } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { t, type NodePanelLang, type StudioServerOption } from "./shared";

type ServerTagsInputProps = {
  lang: NodePanelLang;
  selectedIds: number[];
  servers: StudioServerOption[];
  onAdd: (serverId: number) => void;
  onRemove: (serverId: number) => void;
};

export function ServerTagsInput({
  lang,
  selectedIds,
  servers,
  onAdd,
  onRemove,
}: ServerTagsInputProps) {
  const remainingServers = servers.filter((server) => !selectedIds.includes(server.id));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {selectedIds.length ? (
          selectedIds.map((serverId) => {
            const server = servers.find((item) => item.id === serverId);

            return (
              <div
                key={serverId}
                className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/70 px-3 py-1.5 text-xs"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-2 w-2 rounded-full",
                    server ? "bg-emerald-400" : "bg-muted-foreground/50",
                  )}
                />
                <span className="font-medium text-foreground">
                  {server?.name || `Server #${serverId}`}
                </span>
                {server?.host ? (
                  <span className="text-muted-foreground">{server.host}</span>
                ) : null}
                <button
                  type="button"
                  aria-label={t(lang, "Удалить сервер", "Remove server")}
                  onClick={() => onRemove(serverId)}
                  className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })
        ) : (
          <p className="text-xs text-muted-foreground">
            {t(lang, "Серверы ещё не выбраны.", "No servers attached yet.")}
          </p>
        )}
      </div>

      <Select onValueChange={(value) => onAdd(Number(value))}>
        <div className="relative">
          <Plus className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <SelectTrigger
            className="h-11 rounded-2xl border-dashed border-border/70 bg-background/70 pl-9 text-sm"
            disabled={!remainingServers.length}
          >
            <SelectValue
              placeholder={
                remainingServers.length
                  ? t(lang, "Добавить сервер", "Add server")
                  : t(lang, "Все серверы уже добавлены", "All servers are already added")
              }
            />
          </SelectTrigger>
        </div>
        <SelectContent>
          {remainingServers.map((server) => (
            <SelectItem key={server.id} value={String(server.id)}>
              {server.name} ({server.host})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
