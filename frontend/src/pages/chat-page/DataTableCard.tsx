import { Server } from "lucide-react";

import { cn } from "@/lib/utils";

export type DataTable = {
  title?: string;
  headers?: string[];
  rows?: Array<Array<string | number | boolean | null | undefined>>;
  kind?: string;
  interactive?: boolean;
  empty?: boolean;
  summary?: string;
  items?: Array<Record<string, unknown>>;
};

function cellTone(value: string, header: string): string {
  const h = header.toLowerCase();
  const v = value.toLowerCase();
  if (v === "ok" || v === "true" || v === "yes" || v === "healthy") return "text-success";
  if (v === "fail" || v === "false" || v === "no" || v === "critical" || v === "unreachable") return "text-destructive";
  if (v === "warning") return "text-warning";
  if (h.includes("host") || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value)) return "font-mono text-[11px] text-info/90";
  if (h === "id" || h.includes("порт") || h.includes("port") || h.includes("exit")) {
    return "font-mono tabular-nums text-muted-foreground";
  }
  return "text-foreground/90";
}

function looksLikeServerName(value: string, header: string): boolean {
  const h = header.toLowerCase();
  if (h.includes("имя") || h.includes("name") || h.includes("server") || h.includes("сервер")) {
    return /^[A-Za-z0-9][A-Za-z0-9._-]{1,48}$/.test(value);
  }
  return false;
}

/** Compact dense inventory/data table — minimal padding, no bulky chrome. */
export function DataTableCard({ table }: { table: DataTable }) {
  const headers = table.headers || [];
  const rows = table.rows || [];
  if (!rows.length) return null;

  return (
    <div className="max-w-[min(960px,100%)] overflow-hidden rounded-sm border border-border/60 bg-card/50">
      {table.title ? (
        <div className="flex items-center justify-between gap-2 border-b border-border/50 px-2 py-1">
          <div className="truncate text-[11px] font-medium text-foreground/90">{table.title}</div>
          <div className="shrink-0 font-mono text-[10px] text-muted-foreground">{rows.length}</div>
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left text-[11.5px] leading-4">
          {headers.length ? (
            <thead>
              <tr className="border-b border-border/50 bg-muted/20 text-[10px] text-muted-foreground">
                {headers.map((h) => (
                  <th key={h} className="whitespace-nowrap px-2 py-1 font-medium first:pl-2.5 last:pr-2.5">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {rows.map((row, ri) => (
              <tr
                key={ri}
                className="border-b border-border/30 last:border-0 odd:bg-transparent even:bg-muted/10 hover:bg-primary/[0.04]"
              >
                {row.map((cell, ci) => {
                  const header = headers[ci] || "";
                  const value = cell == null || cell === "" ? "—" : String(cell);
                  const serverish = looksLikeServerName(value, header);
                  return (
                    <td key={ci} className="whitespace-nowrap px-2 py-0.5 align-middle first:pl-2.5 last:pr-2.5">
                      <span className={cn("inline-flex max-w-[14rem] items-center gap-1 truncate", cellTone(value, header))}>
                        {serverish ? <Server className="h-2.5 w-2.5 shrink-0 opacity-70" /> : null}
                        {value}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
