import { cn } from "@/lib/utils";

export function SummaryCard({
  label,
  value,
  hint,
  alert,
}: {
  label: string;
  value: string | number;
  hint: string;
  alert?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border px-3 py-3",
        alert ? "border-destructive/35 bg-destructive/10" : "border-border/70 bg-background/90",
      )}
    >
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-lg font-semibold", alert ? "text-destructive" : "text-foreground")}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}
