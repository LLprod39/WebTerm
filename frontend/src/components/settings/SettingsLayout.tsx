import { useState } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { SettingsIcons } from "@/lib/app-icons";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { fetchAuthSession } from "@/lib/api";
import type { AuthUser } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import {
  allSettingsNavItems,
  canViewSettingsNavItem,
  findSettingsNavItem,
  visibleSettingsNavGroups,
  type SettingsNavItem,
} from "./settings-nav-items";

/** First settings page a non-admin is allowed to open (fallback landing). */
function firstAllowedSettingsPath(user: AuthUser | null | undefined): string {
  return allSettingsNavItems.find((item) => canViewSettingsNavItem(user, item))?.path ?? "/";
}

/** Default landing for /settings — readiness is admin-only. */
export function SettingsIndexRedirect() {
  const { data: authData, isLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  if (isLoading) return null;
  return <Navigate to={firstAllowedSettingsPath(authData?.user)} replace />;
}

function isActivePath(pathname: string, item: SettingsNavItem) {
  return pathname === item.path || pathname.startsWith(`${item.path}/`);
}

function SettingsSideNav({
  user,
  onNavigate,
  className,
}: {
  user: AuthUser | null | undefined;
  onNavigate?: () => void;
  className?: string;
}) {
  const location = useLocation();
  const { lang } = useI18n();
  const groups = visibleSettingsNavGroups(user, Boolean(user?.features.plugins));

  return (
    <nav className={cn("space-y-7", className)} aria-label="Разделы настроек">
      {groups.map((group) => (
        <div key={group.id} className="space-y-2">
          <div className="px-3">
            <div className="type-label text-muted-foreground">
              {localize(lang, group.label, group.labelEn ?? group.label)}
            </div>
            {group.description ? (
              <p className="mt-1 text-xs leading-5 text-muted-foreground/80">
                {localize(lang, group.description, group.descriptionEn ?? group.description)}
              </p>
            ) : null}
          </div>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActivePath(location.pathname, item);
              return (
                <li key={item.id}>
                  <NavLink
                    to={item.path}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex min-h-10 items-center gap-2.5 rounded-sm px-3 py-2 text-sm transition-colors",
                      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                      active
                        ? "bg-primary/10 font-medium text-foreground"
                        : "text-muted-foreground hover:bg-surface-1/80 hover:text-foreground",
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "absolute inset-y-1.5 left-0 w-0.5 rounded-sm transition-opacity",
                        active ? "bg-primary opacity-100" : "opacity-0 group-hover:bg-border group-hover:opacity-100",
                      )}
                    />
                    <Icon
                      className={cn(
                        "h-3.5 w-3.5 shrink-0",
                        active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                      )}
                      strokeWidth={1.5}
                      aria-hidden
                    />
                    <span className="min-w-0 truncate leading-5">
                      {localize(lang, item.label, item.labelEn ?? item.label)}
                    </span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SettingsSidebarHeader({ compact = false }: { compact?: boolean }) {
  const { t, lang } = useI18n();

  return (
    <div
      className={cn(
        "shrink-0 border-b border-border",
        compact ? "px-5 py-5" : "px-4 py-4",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex shrink-0 items-center justify-center rounded-sm border border-primary/25 bg-primary/10 text-primary",
            compact ? "h-10 w-10" : "h-9 w-9",
          )}
        >
          <SettingsIcons.shell className={compact ? "h-5 w-5" : "h-4 w-4"} strokeWidth={1.5} />
        </div>
        <div className="min-w-0 pt-0.5">
          <h1 className={cn("font-display font-bold tracking-tight text-foreground", compact ? "text-lg" : "text-base")}>
            {t("nav.settings")}
          </h1>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
            {localize(lang, "Конфигурация платформы", "Platform configuration")}
          </p>
        </div>
      </div>
    </div>
  );
}

function SettingsMobileMenu({
  user,
  onNavigate,
}: {
  user: AuthUser | null | undefined;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full flex-col bg-card">
      <SettingsSidebarHeader compact />
      <ScrollArea className="min-h-0 flex-1 px-2 py-4">
        <SettingsSideNav user={user} onNavigate={onNavigate} />
      </ScrollArea>
    </div>
  );
}

export default function SettingsLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t, lang } = useI18n();
  const location = useLocation();
  const { data: authData, isLoading: authLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const user = authData?.user;
  const current = findSettingsNavItem(location.pathname);

  // Route-level guard: non-admins hitting an admin-only settings page directly
  // (by URL) are bounced to the settings index, which lands them on an allowed page.
  if (!authLoading && !canViewSettingsNavItem(user, current)) {
    return <Navigate to={firstAllowedSettingsPath(user)} replace />;
  }

  return (
    <div data-ui-slot="settings-layout" className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background">
      {/* Mobile top bar */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="shrink-0">
              <SettingsIcons.menu className="h-5 w-5" strokeWidth={1.5} />
              <span className="sr-only">Открыть меню настроек</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[min(100vw-2rem,20rem)] p-0">
            <SettingsMobileMenu user={user} onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            {current ? localize(lang, current.label, current.labelEn ?? current.label) : t("nav.settings")}
          </div>
          {current?.description ? (
            <div className="truncate text-sm text-muted-foreground">
              {localize(lang, current.description, current.descriptionEn ?? current.description)}
            </div>
          ) : null}
        </div>
      </header>

      <div className="flex min-h-0 w-full flex-1 overflow-hidden">
        {/* Desktop secondary rail — full-height, stays put while content scrolls */}
        <aside
          data-ui-slot="settings-sidebar"
          className="hidden h-full min-h-0 w-[15.5rem] shrink-0 flex-col overflow-hidden border-r border-border bg-card lg:flex xl:w-64"
        >
          <SettingsSidebarHeader />
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-2 py-4">
              <SettingsSideNav user={user} />
            </div>
          </ScrollArea>
        </aside>

        {/* Content */}
        <div
          data-ui-slot="settings-content"
          role="region"
          aria-label={t("nav.settings")}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-background"
        >
          <div className="px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
