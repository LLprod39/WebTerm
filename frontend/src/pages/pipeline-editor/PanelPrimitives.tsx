import type { ReactNode } from "react";
import { CheckCircle2, ChevronDown, Info, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { PipelineRiskSummary } from "@/components/pipeline/pipelineRiskSummary";
import { cn } from "@/lib/utils";

import { localize } from "./presentation";

export function NodeFormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-lg border border-border/70 bg-background/55 px-3 py-3">
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</h4>
        {description ? <p className="text-xs leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function FieldHint({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{children}</p>;
}

export function RunRiskSummaryPanel({ summary, lang }: { summary: PipelineRiskSummary; lang: string }) {
  const levelText =
    summary.level === "safe"
      ? localize(lang, "Безопасно", "Safe")
      : summary.level === "dangerous"
        ? localize(lang, "Нужно подтверждение", "Needs approval")
        : localize(lang, "Проверьте", "Review");
  const toneClass =
    summary.level === "safe"
      ? "border-emerald-500/25 bg-emerald-500/5"
      : summary.level === "dangerous"
        ? "border-red-500/25 bg-red-500/5"
        : "border-amber-500/25 bg-amber-500/5";
  const iconClass =
    summary.level === "safe"
      ? "text-emerald-400"
      : summary.level === "dangerous"
        ? "text-red-400"
        : "text-amber-400";

  return (
    <section className={cn("rounded-xl border px-3 py-3", toneClass)}>
      <div className="flex items-start gap-3">
        {summary.level === "safe" ? (
          <CheckCircle2 className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        ) : summary.level === "dangerous" ? (
          <XCircle className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        ) : (
          <Info className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{localize(lang, "Риск перед запуском", "Risk before run")}</p>
            <Badge variant={summary.level === "safe" ? "outline" : "secondary"} className="text-xs">
              {levelText}
            </Badge>
            {summary.missingApprovalCount > 0 ? (
              <Badge variant="destructive" className="text-xs">
                {localize(lang, `${summary.missingApprovalCount} без подтверждения`, `${summary.missingApprovalCount} missing approval`)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
            <div>{localize(lang, "Изменяющие шаги", "Mutating steps")}: <span className="text-foreground">{summary.mutatingCount}</span></div>
            <div>{localize(lang, "Подтверждения", "Approval gates")}: <span className="text-foreground">{summary.approvalCount}</span></div>
            <div>{localize(lang, "Проверки", "Verification")}: <span className="text-foreground">{summary.verificationCount}</span></div>
          </div>
          {summary.items.length ? (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {summary.items.slice(0, 4).map((item) => (
                <li key={item.nodeId} className="flex items-start gap-1.5">
                  <span className={item.hasApproval ? "text-emerald-400" : "text-red-400"}>{item.hasApproval ? "ok" : "!"}</span>
                  <span>
                    <span className="text-foreground">{item.label}</span>: {item.reason}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              {localize(lang, "Изменяющих действий не найдено.", "No mutating actions detected.")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export function AdvancedDisclosure({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="group rounded-lg border border-dashed border-border/70 bg-muted/10 px-3 py-2"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {title}
        <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}

export function FailureSelect({
  lang,
  value,
  onChange,
}: {
  lang: "en" | "ru";
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{localize(lang, "При ошибке", "On failure")}</Label>
      <Select value={value || "abort"} onValueChange={onChange}>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="abort">{localize(lang, "Остановить pipeline", "Abort pipeline")}</SelectItem>
          <SelectItem value="continue">{localize(lang, "Продолжить", "Continue")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
