import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { emptyValue, filterBlock, lineCountLabel, nonEmptyLines } from "./settingsModel";

export function InfoCard({
  label,
  value,
  mono,
  hint,
  tone = "default",
  lang,
}: {
  label: string;
  value: string | number;
  mono?: boolean;
  hint?: string;
  tone?: "default" | "accent" | "alert";
  lang: string;
}) {
  return (
    <div
      className={cn(
        "rounded-[1.1rem] border p-3 shadow-sm",
        tone === "alert"
          ? "border-destructive/25 bg-destructive/10"
          : tone === "accent"
            ? "border-primary/20 bg-primary/10"
            : "border-border bg-background",
      )}
    >
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1.5 break-words text-sm",
          mono && "font-mono text-xs",
          tone === "alert" ? "text-destructive" : "text-foreground",
        )}
      >
        {value || emptyValue(lang)}
      </div>
      {hint ? <div className="mt-1.5 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function OutputBlock({
  label,
  value,
  query,
  emptyLabel = "No data",
  onCopy,
  lang,
}: {
  label: string;
  value: string;
  query: string;
  emptyLabel?: string;
  onCopy?: () => void;
  lang: string;
}) {
  const filteredValue = filterBlock(value, query);
  const visibleValue = filteredValue || "";

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground">
            {lineCountLabel(lang, nonEmptyLines(visibleValue || value).length)}
          </span>
          {onCopy ? (
            <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={onCopy}>
              <Copy className="mr-1 h-3 w-3" />
              {localize(lang, "Копировать", "Copy")}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-1.5 rounded-[1.1rem] border border-border bg-background p-3">
        <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground">
          {visibleValue || emptyLabel}
        </pre>
      </div>
    </div>
  );
}
