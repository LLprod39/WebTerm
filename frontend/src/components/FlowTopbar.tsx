import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { CalendarDays, ChevronRight, Moon, Search, Sun } from "lucide-react";

import { ConnectionStatusDot } from "@/components/ConnectionStatus";
import { openCommandPalette } from "@/components/FlowChrome";
import { NotificationCenter } from "@/components/NotificationCenter";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { localize, useI18n } from "@/lib/i18n";
import { useUiStyle } from "@/lib/ui-style";
import { cn } from "@/lib/utils";

/** First path segment → nav i18n key (Flow breadcrumb). */
const SECTION_TITLE_KEY: Record<string, string> = {
  dashboard: "nav.dashboard",
  servers: "nav.servers",
  agents: "nav.agents",
  chat: "nav.chat",
  studio: "nav.studio",
  kubernetes: "nav.kubernetes",
  mars: "nav.mars",
  monitoring: "nav.insights",
  settings: "nav.settings",
};

/**
 * Global topbar rendered only under the Flow skin: breadcrumb, search,
 * date chip and the black "Ask AI" CTA (FlowAI reference shell).
 */
export function FlowTopbar() {
  const location = useLocation();
  const { lang, t } = useI18n();
  const { style, setStyle } = useUiStyle();
  const isDark = style === "flow-dark";

  const section = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const titleKey = SECTION_TITLE_KEY[section];
  const sectionTitle = titleKey ? t(titleKey) : section;

  const dateLabel = useMemo(() => {
    return new Date().toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  }, [lang]);

  const isMac =
    typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent);

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border/80 bg-card/90 px-4 backdrop-blur-md">
      <SidebarTrigger className="hidden h-8 w-8 text-muted-foreground hover:text-foreground md:flex" />

      <nav className="flex min-w-0 items-center gap-1.5 text-[13px]" aria-label={localize(lang, "Хлебные крошки", "Breadcrumb")}>
        <Link to="/dashboard" className="shrink-0 text-muted-foreground transition-colors hover:text-foreground">
          WebTerm
        </Link>
        <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/60" aria-hidden />
        <span className="truncate font-medium text-foreground">{sectionTitle}</span>
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={() => openCommandPalette()}
          className={cn(
            "hidden h-9 w-56 items-center gap-2 rounded-lg border border-border bg-card px-3 lg:flex",
            "text-[13px] text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
          )}
          aria-label={localize(lang, "Открыть поиск", "Open search")}
        >
          <Search className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="flex-1 truncate text-left">
            {localize(lang, "Поиск…", "Search for something…")}
          </span>
          <kbd className="rounded border border-border bg-surface-1 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground/80">
            {isMac ? "⌘K" : "Ctrl K"}
          </kbd>
        </button>

        <button
          type="button"
          onClick={() => openCommandPalette()}
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card lg:hidden",
            "text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
          )}
          aria-label={localize(lang, "Поиск", "Search")}
        >
          <Search className="h-4 w-4" aria-hidden />
        </button>

        <span className="hidden h-9 items-center gap-2 rounded-lg border border-border bg-card px-3 text-[12px] text-muted-foreground xl:flex">
          <CalendarDays className="h-3.5 w-3.5" aria-hidden />
          {dateLabel}
        </span>

        <ConnectionStatusDot className="hidden sm:inline-flex px-1" />

        <NotificationCenter />

        <button
          type="button"
          onClick={() => setStyle(isDark ? "flow" : "flow-dark")}
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card",
            "text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
          )}
          aria-label={
            isDark
              ? localize(lang, "Светлая тема", "Switch to light theme")
              : localize(lang, "Тёмная тема", "Switch to dark theme")
          }
          title={
            isDark
              ? localize(lang, "Светлая тема", "Light theme")
              : localize(lang, "Тёмная тема", "Dark theme")
          }
        >
          {isDark ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
        </button>
      </div>
    </header>
  );
}
