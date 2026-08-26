import { useLocation } from "react-router-dom";

import { ConnectionStatusDot } from "@/components/ConnectionStatus";
import { openCommandPalette } from "@/components/FlowChrome";
import { NotificationCenter } from "@/components/NotificationCenter";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { ActionIcons, AppearanceIcons } from "@/lib/app-icons";
import { localize, useI18n } from "@/lib/i18n";
import { isUiStyleId, UI_STYLE_OPTIONS, useUiStyle } from "@/lib/ui-style";

const SECTION_TITLE_KEY: Record<string, string> = {
  dashboard: "nav.dashboard",
  monitoring: "nav.insights",
  servers: "nav.servers",
  automation: "nav.playbooks",
  agents: "nav.agents",
  studio: "nav.studio",
  kubernetes: "nav.kubernetes",
  mars: "nav.mars",
  settings: "nav.settings",
  plugins: "nav.plugins",
};

export function EnterpriseTopbar() {
  const location = useLocation();
  const { lang, t } = useI18n();
  const { style, setStyle } = useUiStyle();
  const section = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const sectionTitle = SECTION_TITLE_KEY[section] ? t(SECTION_TITLE_KEY[section]) : section;

  return (
    <header
      data-ui-slot="enterprise-topbar"
      className="sticky top-0 z-30 flex min-h-16 shrink-0 items-center gap-3 border-b border-border bg-card px-3 sm:px-4 lg:px-5"
    >
      <SidebarTrigger
        className="hidden h-11 w-11 shrink-0 border border-border bg-surface-0 text-muted-foreground hover:bg-secondary hover:text-foreground md:flex"
      />

      <div className="min-w-0 lg:w-64">
        <span className="truncate text-sm font-semibold text-foreground">{sectionTitle}</span>
      </div>

      <button
        type="button"
        onClick={() => openCommandPalette()}
        className="mx-auto hidden h-11 w-full max-w-xl items-center gap-3 rounded-md border border-border bg-surface-0 px-3 text-left text-sm text-muted-foreground transition-colors hover:border-border-strong hover:bg-card hover:text-foreground lg:flex"
        aria-label={localize(lang, "Открыть поиск", "Open search")}
      >
        <ActionIcons.search className="h-4 w-4 shrink-0" strokeWidth={1.5} aria-hidden />
        <span className="flex-1 truncate">{localize(lang, "Найти сервер, запуск или настройку…", "Find a server, run, or setting…")}</span>
        <kbd className="rounded border border-border bg-card px-2 py-1 font-mono text-[10px] text-foreground">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
        <button
          type="button"
          onClick={() => openCommandPalette()}
          className="flex h-11 w-11 items-center justify-center rounded-md border border-border bg-surface-0 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
          aria-label={localize(lang, "Поиск", "Search")}
        >
          <ActionIcons.search className="h-4 w-4" strokeWidth={1.5} aria-hidden />
        </button>

        <div className="hidden h-11 w-11 items-center justify-center rounded-md border border-border bg-surface-0 md:flex">
          <ConnectionStatusDot className="px-0" />
        </div>

        <NotificationCenter />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex h-11 w-11 items-center justify-center rounded-md border border-primary/25 bg-primary/8 text-primary transition-colors hover:bg-primary/14"
              aria-label={localize(lang, "Сменить стиль интерфейса", "Change interface style")}
              title={localize(lang, "Сменить стиль", "Change style")}
            >
              <AppearanceIcons.picker className="h-4 w-4" strokeWidth={1.5} aria-hidden />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="max-h-[min(var(--radix-dropdown-menu-content-available-height),32rem)] w-80 overflow-y-auto p-2"
          >
            <DropdownMenuLabel className="px-2 py-2">
              <div className="text-sm font-semibold text-foreground">{localize(lang, "Стиль интерфейса", "Interface style")}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup
              value={style}
              onValueChange={(value) => {
                if (isUiStyleId(value)) setStyle(value);
              }}
            >
              {UI_STYLE_OPTIONS.map((option) => (
                <DropdownMenuRadioItem key={option.id} value={option.id} className="min-h-12 gap-2 py-2 pl-8 pr-2">
                  <span className="flex items-center gap-1" aria-hidden>
                    {option.swatches.slice(0, 3).map((color) => (
                      <span key={color} className="h-3 w-3 rounded-[2px] border border-border-strong" style={{ background: color }} />
                    ))}
                  </span>
                  <span className="min-w-0 truncate text-xs font-medium">
                    {lang === "ru" ? option.labelRu : option.labelEn}
                  </span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
