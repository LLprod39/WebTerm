import { AppearanceIcons } from "@/lib/app-icons";
import { localize, useI18n } from "@/lib/i18n";
import { UI_STYLE_OPTIONS, useUiStyle, type UiStyleId } from "@/lib/ui-style";
import { cn } from "@/lib/utils";

function ThemeChromePreview({ swatches }: { swatches: string[] }) {
  const canvas = swatches[0] ?? "#111111";
  const ink = swatches[1] ?? "#888888";
  const accent = swatches[2] ?? "#4a90e2";
  const accentAlt = swatches[3] ?? accent;

  return (
    <div
      className="relative aspect-[16/10] w-full overflow-hidden"
      style={{ background: canvas }}
      aria-hidden
    >
      <div
        className="absolute inset-2.5 flex overflow-hidden rounded-[3px]"
        style={{ boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${ink} 18%, transparent)` }}
      >
        <div className="flex w-[22%] shrink-0 flex-col gap-1 p-1.5" style={{ background: ink }}>
          <span className="h-1 w-[70%] rounded-[1px]" style={{ background: accent }} />
          <span
            className="mt-0.5 h-1 w-full rounded-[1px] opacity-55"
            style={{ background: canvas }}
          />
          <span className="h-1 w-[82%] rounded-[1px] opacity-35" style={{ background: canvas }} />
          <span className="h-1 w-[64%] rounded-[1px] opacity-28" style={{ background: canvas }} />
          <span
            className="mt-auto h-1.5 w-full rounded-[1px] opacity-70"
            style={{ background: accentAlt }}
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-1.5" style={{ background: canvas }}>
          <div className="flex items-center gap-1">
            <span className="h-1 w-[36%] rounded-[1px] opacity-55" style={{ background: ink }} />
            <span className="ml-auto h-1.5 w-1.5 rounded-[1px]" style={{ background: accent }} />
          </div>

          <div className="flex min-h-0 flex-1 gap-1.5">
            <div
              className="flex flex-1 flex-col gap-1 rounded-[2px] p-1.5"
              style={{
                background: `color-mix(in srgb, ${ink} 12%, ${canvas})`,
                boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${ink} 14%, transparent)`,
              }}
            >
              <span className="h-1 w-[72%] rounded-[1px] opacity-70" style={{ background: ink }} />
              <span className="h-1 w-[48%] rounded-[1px] opacity-35" style={{ background: ink }} />
              <span
                className="mt-auto h-1 w-[40%] rounded-[1px]"
                style={{ background: accent }}
              />
            </div>
            <div
              className="flex w-[38%] flex-col gap-1 rounded-[2px] p-1.5"
              style={{
                background: `color-mix(in srgb, ${ink} 8%, ${canvas})`,
                boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${ink} 12%, transparent)`,
              }}
            >
              <span className="h-1 w-full rounded-[1px]" style={{ background: accentAlt }} />
              <span className="h-1 w-[78%] rounded-[1px] opacity-40" style={{ background: ink }} />
              <span className="h-1 w-[55%] rounded-[1px] opacity-25" style={{ background: ink }} />
            </div>
          </div>
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 flex h-1.5">
        {swatches.map((color) => (
          <span key={color} className="min-w-0 flex-1" style={{ background: color }} />
        ))}
      </div>
    </div>
  );
}

function ThemeOptionCard({
  option,
  selected,
  label,
  blurb,
  activeLabel,
  onSelect,
  index,
}: {
  option: (typeof UI_STYLE_OPTIONS)[number];
  selected: boolean;
  label: string;
  blurb: string;
  activeLabel: string;
  onSelect: (id: UiStyleId) => void;
  index: number;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(option.id)}
      aria-pressed={selected}
      aria-label={label}
      style={{ animationDelay: `${Math.min(index, 10) * 35}ms` }}
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-sm border text-left",
        "animate-in fade-in-0 slide-in-from-bottom-2 duration-300 motion-reduce:animate-none",
        "transition-[border-color,background-color,box-shadow,transform] duration-150 motion-reduce:transition-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        selected
          ? "border-primary bg-primary/8 shadow-elev-1"
          : "border-border bg-surface-0 hover:-translate-y-0.5 hover:border-border-strong hover:bg-secondary/30 hover:shadow-elev-1 motion-reduce:hover:transform-none",
      )}
    >
      <div className="relative border-b border-border/70">
        <ThemeChromePreview swatches={option.swatches} />
        {selected ? (
          <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-sm bg-primary text-primary-foreground shadow-elev-1">
            <AppearanceIcons.selected className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </span>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col gap-1.5 p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-sm font-semibold tracking-tight text-foreground">
            {label}
          </span>
          {selected ? (
            <span className="type-label text-[10px] text-primary">{activeLabel}</span>
          ) : null}
        </div>
        <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{blurb}</p>
      </div>
    </button>
  );
}

export function UiStylePicker({
  className,
  showIntro = true,
}: {
  className?: string;
  showIntro?: boolean;
}) {
  const { lang } = useI18n();
  const { style, setStyle } = useUiStyle();
  const activeLabel = localize(lang, "Активна", "Active");

  return (
    <section
      data-ui-slot="style-picker"
      className={cn(
        showIntro
          ? "rounded-sm border border-border bg-card p-4 shadow-elev-1"
          : "rounded-sm border border-border bg-card/60 p-3 shadow-elev-1 sm:p-4",
        className,
      )}
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

      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,17rem),1fr))]">
        {UI_STYLE_OPTIONS.map((option, index) => (
          <ThemeOptionCard
            key={option.id}
            option={option}
            selected={style === option.id}
            label={lang === "ru" ? option.labelRu : option.labelEn}
            blurb={lang === "ru" ? option.blurbRu : option.blurbEn}
            activeLabel={activeLabel}
            onSelect={setStyle}
            index={index}
          />
        ))}
      </div>
    </section>
  );
}
