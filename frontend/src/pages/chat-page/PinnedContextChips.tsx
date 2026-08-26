import { Server, X } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";

import type { PinnedServer } from "./ComposeCommandPalette";

export function PinnedContextChips({
  servers,
  onUnpinServer,
}: {
  servers: PinnedServer[];
  onUnpinServer: (id: number) => void;
}) {
  const { lang } = useI18n();
  if (!servers.length) return null;

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5 px-0.5">
      <span className="mr-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
        {localize(lang, "Сервер", "Server")}
      </span>
      {servers.map((s) => (
        <span
          key={`s-${s.id}`}
          className="inline-flex max-w-[14rem] items-center gap-1 rounded-sm border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
        >
          <Server className="h-3 w-3 shrink-0 opacity-80" strokeWidth={1.75} />
          <span className="truncate font-medium tracking-tight">{s.name}</span>
          <button
            type="button"
            className="rounded-sm p-0.5 opacity-70 hover:bg-primary/20 hover:opacity-100"
            onClick={() => onUnpinServer(s.id)}
            aria-label={localize(lang, "Открепить", "Unpin")}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
