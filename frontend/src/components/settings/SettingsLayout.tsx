import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Menu, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { fetchAuthSession } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { settingsNavGroups, type SettingsNavGroup, type SettingsNavItem } from "./settings-nav-items";

function visibleSettingsGroups(isAdmin: boolean): SettingsNavGroup[] {
  return settingsNavGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.adminOnly || isAdmin),
    }))
    .filter((group) => group.items.length > 0);
}

function isActivePath(pathname: string, item: SettingsNavItem) {
  return pathname === item.path || pathname.startsWith(`${item.path}/`);
}

function SettingsNavPill({
  item,
  isActive,
  onNavigate,
}: {
  item: SettingsNavItem;
  isActive: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      onClick={onNavigate}
      className={cn(
        "inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isActive
          ? "border-primary/35 bg-primary/12 text-primary"
          : "border-border/70 bg-secondary/20 text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{item.label}</span>
    </NavLink>
  );
}

function SettingsDesktopNav({ isAdmin }: { isAdmin: boolean }) {
  const location = useLocation();
  const { t } = useI18n();
  const groups = visibleSettingsGroups(isAdmin);

  return (
    <section className="mb-6 hidden rounded-xl border border-border/70 bg-card/70 px-4 py-4 shadow-sm lg:block">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
            <Settings className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">{t("nav.settings")}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">{t("settings.subtitle")}</p>
          </div>
        </div>
        <p className="max-w-md text-sm leading-6 text-muted-foreground">{t("settings.hint")}</p>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-3">
        {groups.map((group) => (
          <div key={group.id} className="min-w-0 rounded-lg border border-border/60 bg-background/40 px-3 py-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
            </div>
            <div className="flex flex-wrap gap-2">
              {group.items.map((item) => (
                <SettingsNavPill
                  key={item.id}
                  item={item}
                  isActive={isActivePath(location.pathname, item)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SettingsMobileMenu({
  isAdmin,
  onNavigate,
}: {
  isAdmin: boolean;
  onNavigate?: () => void;
}) {
  const location = useLocation();
  const { t } = useI18n();
  const groups = visibleSettingsGroups(isAdmin);

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
            <Settings className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-foreground">{t("nav.settings")}</h2>
            <p className="text-sm text-muted-foreground">{t("settings.subtitle")}</p>
          </div>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-4 py-4">
        <nav className="space-y-5" aria-label="Settings sections">
          {groups.map((group) => (
            <div key={group.id}>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.label}
              </div>
              <div className="space-y-2">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActivePath(location.pathname, item);
                  return (
                    <NavLink
                      key={item.id}
                      to={item.path}
                      onClick={onNavigate}
                      className={cn(
                        "flex min-h-12 items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                        active
                          ? "border-primary/35 bg-primary/12 text-primary"
                          : "border-border/70 bg-card text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <div className="min-w-0">
                        <div className="font-medium">{item.label}</div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground">{item.description}</div>
                      </div>
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </ScrollArea>
    </div>
  );
}

export default function SettingsLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useI18n();
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-14 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="shrink-0">
              <Menu className="h-5 w-5" />
              <span className="sr-only">Открыть меню настроек</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-80 p-0">
            <SettingsMobileMenu isAdmin={isAdmin} onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
        <div className="flex min-w-0 items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          <span className="truncate font-semibold">{t("nav.settings")}</span>
        </div>
      </header>

      <main className="relative min-h-0 flex-1 overflow-auto bg-background">
        <div className="relative z-0 mx-auto max-w-[1280px] px-4 py-6 lg:px-8 lg:py-8">
          <SettingsDesktopNav isAdmin={isAdmin} />
          <Outlet />
        </div>
      </main>
    </div>
  );
}
