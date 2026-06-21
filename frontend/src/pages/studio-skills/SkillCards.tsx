import ReactMarkdown from "react-markdown";
import { AlertTriangle, CheckCircle2, Server, Shield } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { StudioSkill, StudioSkillValidationResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

import { safetyLevelLabel } from "./skillScaffold";

export function SkillMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        code: ({ className, children }) => {
          const code = String(children).replace(/\n$/, "");
          if ((className || "").includes("language-") || code.includes("\n")) {
            return (
              <code className="block whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-4 font-mono text-[12.5px] leading-6 text-foreground">
                {code}
              </code>
            );
          }
          return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">{children}</code>;
        },
        h1: ({ children }) => <h1 className="mt-2 text-xl font-bold tracking-tight text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-6 text-lg font-semibold text-foreground">{children}</h2>,
        h3: ({ children }) => (
          <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>
        ),
        p: ({ children }) => <p className="my-2 text-sm leading-7 text-foreground/85">{children}</p>,
        ul: ({ children }) => <ul className="list-disc space-y-1.5 pl-5 text-sm leading-7 text-foreground/85">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-7 text-foreground/85">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="my-3 border-l-2 border-primary/40 pl-4 text-sm italic text-muted-foreground">{children}</blockquote>
        ),
        hr: () => <hr className="my-5 border-border" />,
        pre: ({ children }) => <pre className="overflow-auto">{children}</pre>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

type SkillCardProps = {
  skill: StudioSkill;
  isSelected: boolean;
  onSelect: () => void;
  lang: "ru" | "en";
};

export function SkillCard({ skill, isSelected, onSelect, lang }: SkillCardProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group relative w-full overflow-hidden rounded-xl border p-4 text-left transition-all duration-300 ${
        isSelected
          ? "border-primary/50 bg-primary/5 shadow-md shadow-primary/5 ring-1 ring-primary/20"
          : "border-border/60 bg-background/40 hover:border-border/90 hover:bg-background/60 hover:shadow-lg"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className={`text-[15px] font-semibold ${isSelected ? "text-primary dark:text-primary/90" : "text-foreground"}`}>
              {skill.name}
            </p>
            {skill.runtime_enforced ? (
              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-xs font-bold uppercase tracking-wider text-amber-500">
                {tr("контроль", "enforced")}
              </span>
            ) : null}
            {skill.is_owner ? (
              <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                {tr("Мой", "Mine")}
              </Badge>
            ) : null}
            {!skill.is_owner && skill.owner_username ? (
              <Badge variant="outline" className="px-1.5 py-0 text-xs">
                {tr("Владелец", "Owner")}: {skill.owner_username}
              </Badge>
            ) : null}
            {skill.is_shared ? (
              <Badge variant="outline" className="px-1.5 py-0 text-xs">
                {tr("Общий", "Shared")}
              </Badge>
            ) : null}
            {skill.can_edit === false ? (
              <Badge variant="outline" className="px-1.5 py-0 text-xs opacity-70">
                {tr("Только чтение", "Read only")}
              </Badge>
            ) : null}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
            {skill.service ? (
              <span className="flex items-center gap-1">
                <Server className="h-3 w-3" />
                {skill.service}
              </span>
            ) : null}
            {skill.category ? <span className="opacity-80">· {skill.category}</span> : null}
          </div>
        </div>
        {skill.safety_level ? (
          <Badge variant="outline" className="shrink-0 bg-background/50 px-1.5 py-0 text-xs shadow-sm">
            {safetyLevelLabel(skill.safety_level, lang)}
          </Badge>
        ) : null}
      </div>
      {skill.description ? (
        <p className="mt-3 line-clamp-2 text-[12px] leading-relaxed text-muted-foreground transition-colors group-hover:text-muted-foreground/90">
          {skill.description}
        </p>
      ) : null}
      {skill.guardrail_summary?.length > 0 ? (
        <div className="mt-3 flex items-start gap-1.5 text-xs leading-snug text-emerald-600/80 dark:text-emerald-400/80">
          <Shield className="mt-0.5 h-3 w-3 min-w-[12px]" />
          <p className="line-clamp-1">{skill.guardrail_summary[0]}</p>
        </div>
      ) : null}
      {skill.tags?.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {skill.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${
                isSelected ? "bg-primary/10 text-primary" : "bg-muted/50 text-muted-foreground"
              }`}
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </button>
  );
}

export function ValidationSummaryCard({ report }: { report: StudioSkillValidationResponse }) {
  const { lang } = useI18n();
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const ok = report.summary.is_valid;
  return (
    <Card className="border-border/70 bg-background/24 shadow-none">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-2">
          {ok ? <CheckCircle2 className="h-4 w-4 text-green-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
          <div>
            <p className="text-sm font-medium">
              {ok
                ? tr("Библиотека скиллов прошла валидацию", "Skill library passed validation")
                : tr("Библиотека скиллов требует проверки", "Skill library needs review")}
            </p>
            <p className="text-xs text-muted-foreground">
              {report.summary.skills} {tr("скиллов", "skill(s)")}, {report.summary.errors} {tr("ошибок", "error(s)")},{" "}
              {report.summary.warnings} {tr("предупреждений", "warning(s)")}
            </p>
          </div>
        </div>
        <Badge variant="outline" className="text-xs">
          {report.summary.strict ? tr("строгий режим", "strict mode") : tr("стандартный режим", "standard mode")}
        </Badge>
      </CardContent>
    </Card>
  );
}
