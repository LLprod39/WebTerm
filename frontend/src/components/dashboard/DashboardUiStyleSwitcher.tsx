import { Check, Palette } from "lucide-react";

import { useI18n, localize } from "@/lib/i18n";
import { UI_STYLE_OPTIONS, useUiStyle, type UiStyleId } from "@/lib/ui-style";
import { cn } from "@/lib/utils";

/**
 * Compact style switcher for dashboards — available to every signed-in user.
 * Preference is stored per account (localStorage by user id).
 */
export function DashboardUiStyleSwitcher({ className }: { className?: string }) {
  const { lang } = useI18n();
  const { style, setStyle } = useUiStyle();

  return (
    <section
      className={cn(
        "rounded-sm border border-border bg-card p-4 shadow-elev-1",
        className,
      )}
      aria-label={localize(lang, "Стиль интерфейса", "Interface style")}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/12 text-primary">
            <Palette className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-sm font-bold tracking-tight text-foreground">
              {localize(lang, "Стиль интерфейса", "Interface style")}
            </h2>
            <p className="text-2xs leading-4 text-muted-foreground">
              {localize(
                lang,
                "Только ваш аккаунт. Других пользователей не затрагивает.",
                "Your account only. Does not affect other users.",
              )}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {UI_STYLE_OPTIONS.map((option) => {
          const selected = style === option.id;
          const officialPilotTheme = option.id === "flow-dark";
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setStyle(option.id as UiStyleId)}
              aria-pressed={selected}
              className={cn(
                "relative flex flex-col gap-2 rounded-sm border p-3 text-left transition-colors",
                selected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-surface-0 hover:border-border-strong hover:bg-secondary/40",
              )}
            >
              <div className="flex items-center gap-1.5">
                {option.swatches.map((color) => (
                  <span
                    key={color}
                    className="h-4 w-4 rounded-sm border border-border"
                    style={{ background: color }}
                    aria-hidden
                  />
                ))}
                {selected ? (
                  <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-sm bg-primary text-primary-foreground">
                    <Check className="h-3 w-3" aria-hidden />
                  </span>
                ) : null}
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-foreground">
                  <span>{lang === "ru" ? option.labelRu : option.labelEn}</span>
                  <span className={cn(
                    "rounded-full border px-1.5 py-0.5 text-xs font-medium",
                    officialPilotTheme
                      ? "border-success/35 bg-success/10 text-success"
                      : "border-border bg-secondary/50 text-muted-foreground",
                  )}>
                    {officialPilotTheme
                      ? localize(lang, "Пилот", "Pilot")
                      : localize(lang, "Эксперимент", "Experimental")}
                  </span>
                </div>
                <div className="mt-0.5 text-2xs leading-4 text-muted-foreground">
                  {lang === "ru" ? option.blurbRu : option.blurbEn}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
