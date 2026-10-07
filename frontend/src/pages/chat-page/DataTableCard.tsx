import { Server } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
} from "@/boardui/components/base/table/table";
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
  return "";
}

function looksLikeServerName(value: string, header: string): boolean {
  const h = header.toLowerCase();
  if (h.includes("имя") || h.includes("name") || h.includes("server") || h.includes("сервер")) {
    return /^[A-Za-z0-9][A-Za-z0-9._-]{1,48}$/.test(value);
  }
  return false;
}

/** Inventory/data table using official BoardUI Table primitive. */
export function DataTableCard({ table }: { table: DataTable }) {
  const headers = table.headers || [];
  const rows = table.rows || [];
  if (!rows.length) return null;
  const columnCount = Math.max(headers.length, ...rows.map((row) => row.length));
  const cols = headers.length
    ? headers
    : Array.from({ length: columnCount }, (_, i) => `col-${i + 1}`);

  return (
    <div className="max-w-[min(960px,100%)] overflow-hidden rounded-2xl border border-border-button-default bg-background-primary-default shadow-xs">
      {table.title ? (
        <div className="flex items-center justify-between gap-2 border-b border-border-button-default px-3 py-2">
          <div className="truncate text-body-medium text-text-primary">{table.title}</div>
          <div className="shrink-0 font-mono text-caption-1-medium text-text-tertiary">{rows.length}</div>
        </div>
      ) : null}
      <Table aria-label={table.title || "Data table"} size="sm" containerClassName="min-w-0">
        <TableHeader>
          {cols.map((h) => (
            <TableColumn key={h} isRowHeader={h === cols[0]}>
              {headers.length ? h : ""}
            </TableColumn>
          ))}
        </TableHeader>
        <TableBody>
          {rows.map((row, ri) => (
            <TableRow key={ri}>
              {cols.map((header, ci) => {
                const cell = row[ci];
                const value = cell == null || cell === "" ? "—" : String(cell);
                const serverish = looksLikeServerName(value, headers[ci] || header);
                return (
                  <TableCell key={`${ri}-${ci}`}>
                    <span className={cn("inline-flex max-w-[14rem] items-center gap-1 truncate", cellTone(value, headers[ci] || ""))}>
                      {serverish ? <Server className="h-2.5 w-2.5 shrink-0 opacity-70" /> : null}
                      {value}
                    </span>
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
