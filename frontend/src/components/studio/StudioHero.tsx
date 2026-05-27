import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

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

  return (
    <div className="px-6 py-6 pb-4 shrink-0">
      <section className="relative overflow-hidden rounded-2xl border border-border/50 bg-gradient-to-b from-primary/5 via-background/40 to-background/20 px-6 py-8 shadow-sm backdrop-blur-xl">
        <div className="absolute top-0 left-0 h-[1px] w-full bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
        <div className="relative z-10 flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl space-y-4">
            <div className="flex items-center gap-4">
              {backTo !== undefined && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10 shrink-0 rounded-full bg-background/50 backdrop-blur-md hover:bg-background/80"
                  onClick={() => navigate(backTo)}
                >
                  <ArrowLeft className="h-5 w-5 text-muted-foreground" />
                </Button>
              )}
              <div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex h-6 items-center rounded-full bg-primary/10 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-primary ring-1 ring-primary/20">
                    {kicker}
                  </span>
                </div>
                <h1 className="mt-2 flex items-center gap-2.5 text-3xl font-bold tracking-tight text-foreground">
                  {titleIcon}
                  {title}
                </h1>
              </div>
            </div>

            {description && (
              <p className="max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}

            {stats && (
              <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
                {stats}
              </div>
            )}
          </div>

          {actions && (
            <div className="flex flex-wrap items-center gap-3 pt-2 xl:justify-end">
              {actions}
            </div>
          )}
        </div>
      </section>
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
    <div className="flex items-center gap-1.5 rounded-full bg-background/40 px-3 py-1 ring-1 ring-border/50">
      {icon}
      <span>{label}</span>
    </div>
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
      <Button
        size="sm"
        onClick={onClick}
        className="h-10 gap-2 rounded-full bg-primary px-5 font-medium text-primary-foreground shadow-sm shadow-primary/20 transition-all hover:bg-primary/90 hover:shadow-md"
      >
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
      className="h-10 gap-2 rounded-full px-4 font-medium shadow-sm border-border/50 hover:bg-background/80"
    >
      {icon}
      {label}
    </Button>
  );
}
