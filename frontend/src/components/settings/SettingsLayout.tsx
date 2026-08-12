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
    <nav className={cn("space-y-6", className)} aria-label="Разделы настроек">
      {groups.map((group) => (
        <div key={group.id}>
          <div className="mb-2 px-2">
            <div className="type-label text-muted-foreground">{localize(lang, group.label, group.labelEn ?? group.label)}</div>
            {group.description ? (
              <p className="mt-1 text-xs leading-4 text-muted-foreground">{localize(lang, group.description, group.descriptionEn ?? group.description)}</p>
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
                    className={cn(
                      "group flex min-h-11 items-start gap-2.5 rounded-sm border px-2.5 py-2 text-sm transition-colors",
                      active
                        ? "border-primary/40 bg-primary/12 text-foreground shadow-elev-1"
                        : "border-transparent text-muted-foreground hover:border-border hover:bg-surface-1 hover:text-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border",
                        active
                          ? "border-primary/35 bg-primary/15 text-primary"
                          : "border-border bg-surface-0 text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className={cn("block font-medium leading-5", active && "text-foreground")}>
                        {localize(lang, item.label, item.labelEn ?? item.label)}
                      </span>
                      <span className="mt-0.5 block text-xs leading-4 text-muted-foreground">
                        {localize(lang, item.description, item.descriptionEn ?? item.description)}
                      </span>
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

function SettingsMobileMenu({
  user,
  onNavigate,
}: {
  user: AuthUser | null | undefined;
  onNavigate?: () => void;
}) {
  const { t } = useI18n();

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-sm border border-primary/25 bg-primary/10">
            <SettingsIcons.shell className="h-5 w-5 text-primary" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-base font-bold text-foreground">{t("nav.settings")}</h2>
            <p className="text-sm text-muted-foreground">{t("settings.subtitle")}</p>
          </div>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1 px-3 py-4">
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
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Mobile top bar */}
      <header className="flex h-14 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
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
          <div className="truncate font-semibold text-foreground">
            {current ? localize(lang, current.label, current.labelEn ?? current.label) : t("nav.settings")}
          </div>
          {current?.description ? (
            <div className="truncate text-xs text-muted-foreground">{localize(lang, current.description, current.descriptionEn ?? current.description)}</div>
          ) : null}
        </div>
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-[1400px] flex-1">
        {/* Desktop sidebar */}
        <aside className="hidden w-72 shrink-0 border-r border-border bg-surface-0/40 lg:flex lg:flex-col">
          <div className="border-b border-border px-4 py-5">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 text-primary">
                <SettingsIcons.shell className="h-5 w-5" strokeWidth={1.5} />
              </div>
              <div className="min-w-0">
                <h1 className="font-display text-lg font-bold tracking-tight text-foreground">
                  {t("nav.settings")}
                </h1>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {t("settings.subtitle")}
                </p>
              </div>
            </div>
            <p className="mt-3 rounded-sm border border-border bg-card/80 px-3 py-2 text-2xs leading-4 text-muted-foreground">
              {t("settings.hint")}
            </p>
          </div>
          <ScrollArea className="min-h-0 flex-1 px-2 py-4">
            <SettingsSideNav user={user} />
          </ScrollArea>
        </aside>

        {/* Content */}
        <div role="region" aria-label={t("nav.settings")} className="min-h-0 min-w-0 flex-1 overflow-auto">
          <div className="px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
