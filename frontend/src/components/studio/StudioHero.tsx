import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function StudioHero({
  kicker,
  title,
  titleIcon,
  description,
  stats,
  actions,
  backTo,
}: {
  kicker: string;
  title: ReactNode;
  titleIcon?: ReactNode;
  description?: ReactNode;
  stats?: ReactNode;
  actions?: ReactNode;
  backTo?: string;
}) {
  const navigate = useNavigate();
  const { lang } = useI18n();
  const backLabel = localize(lang, "Назад", "Back");

  return (
    <div className="shrink-0 px-4 pb-2 pt-5 md:px-6">
      <header
        data-ui-slot="studio-hero"
        className="relative overflow-hidden rounded-sm border border-border bg-card px-5 py-5 sm:px-6"
      >
        <div aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-primary opacity-80" />
        <div className="relative flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 max-w-3xl space-y-2">
            <div className="flex items-start gap-3">
              {backTo !== undefined ? (
                <Button
                  variant="ghost"
                  size="icon"
                  className="mt-0.5 h-10 w-10 shrink-0 rounded-sm"
                  onClick={() => navigate(backTo)}
                  aria-label={backLabel}
                  title={backLabel}
                >
                  <ArrowLeft className="h-5 w-5 text-muted-foreground" aria-hidden />
                </Button>
              ) : null}
              <div className="min-w-0">
                <div className="type-label text-muted-foreground">{kicker}</div>
                <h1 className="mt-1 flex items-center gap-2.5 type-h1 text-foreground">
                  {titleIcon}
                  {title}
                </h1>
              </div>
            </div>

            {description ? (
              <p className="max-w-2xl type-body text-muted-foreground">{description}</p>
            ) : null}

            {stats ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
                {stats}
              </div>
            ) : null}
          </div>

          {actions ? (
            <div className="flex w-full flex-wrap items-center gap-2 xl:w-auto xl:justify-end">
              {actions}
            </div>
          ) : null}
        </div>
      </header>
    </div>
  );
}

export function HeroStatChip({
  icon,
  label,
}: {
  icon?: ReactNode;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono tabular-nums">
      {icon}
      <span>{label}</span>
    </span>
  );
}

export function HeroActionButton({
  onClick,
  icon,
  label,
  primary,
}: {
  onClick: () => void;
  icon?: ReactNode;
  label: string;
  primary?: boolean;
}) {
  if (primary) {
    return (
      <Button size="sm" onClick={onClick} className="h-10 gap-2 rounded-sm px-4 font-medium">
        {icon}
        {label}
      </Button>
    );
  }
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      className={cn("h-10 gap-2 rounded-sm px-4 font-medium")}
    >
      {icon}
      {label}
    </Button>
  );
}
