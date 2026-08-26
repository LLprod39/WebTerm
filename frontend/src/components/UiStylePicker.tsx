import { AppearanceIcons } from "@/lib/app-icons";
import { localize, useI18n } from "@/lib/i18n";
import { isEnterpriseStyle, UI_STYLE_OPTIONS, useUiStyle } from "@/lib/ui-style";
import { cn } from "@/lib/utils";

export function UiStylePicker({
  className,
  showIntro = true,
}: {
  className?: string;
  showIntro?: boolean;
}) {
  const { lang } = useI18n();
  const { style, setStyle } = useUiStyle();

  return (
    <section
      data-ui-slot="style-picker"
      className={cn("rounded-sm border border-border bg-card p-4 shadow-elev-1", className)}
      aria-label={localize(lang, "Стиль интерфейса", "Interface style")}
    >
      {showIntro ? (
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/10 text-primary">
            <AppearanceIcons.picker className="h-5 w-5" strokeWidth={1.5} aria-hidden />
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-base font-semibold tracking-tight text-foreground">
              {localize(lang, "Стиль интерфейса", "Interface style")}
            </h2>
            <p className="mt-0.5 max-w-2xl text-xs leading-5 text-muted-foreground">
              {localize(lang, "Чат сохраняет текущее оформление.", "Chat keeps its current design.")}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {UI_STYLE_OPTIONS.map((option) => {
          const selected = style === option.id;

          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setStyle(option.id)}
              aria-pressed={selected}
              className={cn(
                "group relative min-h-32 overflow-hidden rounded-sm border p-4 text-left transition-[border-color,background-color,box-shadow,transform] duration-150",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                selected
                  ? "border-primary bg-primary/8 shadow-elev-1"
                  : "border-border bg-surface-0 hover:-translate-y-0.5 hover:border-border-strong hover:bg-secondary/35 hover:shadow-elev-1",
                isEnterpriseStyle(option.id) && "sm:col-span-2 xl:col-span-1",
              )}
            >
              <div className="flex items-start gap-3">
                <div className="flex shrink-0 items-center gap-1.5 rounded-sm border border-border bg-card p-1.5" aria-hidden>
                  {option.swatches.map((color) => (
                    <span key={color} className="h-5 w-5 rounded-[3px] border border-border-strong" style={{ background: color }} />
                  ))}
                </div>
                {selected ? (
                  <span className="ml-auto flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
                    <AppearanceIcons.selected className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  </span>
                ) : null}
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  {lang === "ru" ? option.labelRu : option.labelEn}
                </span>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {lang === "ru" ? option.blurbRu : option.blurbEn}
              </p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
