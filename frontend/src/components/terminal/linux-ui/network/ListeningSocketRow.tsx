import type { LinuxUiListeningSocket } from "@/lib/api";
import { cn } from "@/lib/utils";

export function extractSocketPort(localAddress: string) {
  const raw = String(localAddress || "").trim();
  if (!raw) return "";
  const bracketMatch = raw.match(/\]:(\d+)$/);
  if (bracketMatch?.[1]) return bracketMatch[1];
  const plainMatch = raw.match(/:(\d+)$/);
  return plainMatch?.[1] || "";
}

export function isSocketExposed(localAddress: string) {
  const raw = String(localAddress || "").trim().toLowerCase();
  return (
    raw.startsWith("0.0.0.0:") ||
    raw.startsWith("[::]:") ||
    raw.startsWith("*:") ||
    raw.startsWith(":::") ||
    raw === "::"
  );
}

export function ListeningSocketRow({
  item,
  selected,
  onClick,
}: {
  item: LinuxUiListeningSocket;
  selected: boolean;
  onClick: () => void;
}) {
  const exposed = isSocketExposed(item.local_address);

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
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.protocol}
        </span>
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.state || "unknown"}
        </span>
        {exposed ? (
          <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-destructive">
            exposed
          </span>
        ) : null}
        {extractSocketPort(item.local_address) ? (
          <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            port {extractSocketPort(item.local_address)}
          </span>
        ) : null}
      </div>
      <div className="mt-2 font-mono text-xs text-foreground">{item.local_address || "n/a"}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{item.process || item.peer_address || "Process metadata unavailable"}</div>
    </button>
  );
}
