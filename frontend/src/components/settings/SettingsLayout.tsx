import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Menu, Settings } from "lucide-react";
import { fetchAuthSession } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { settingsNavGroups, type SettingsNavItem } from "./settings-nav-items";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";

function NavItem({ item, isActive }: { item: SettingsNavItem; isActive: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      className={cn(
        "group relative flex min-h-[60px] items-center gap-3 overflow-hidden rounded-xl border px-3 py-2.5 text-sm font-medium transition-colors duration-150",
        isActive
          ? "border-primary/20 bg-primary/10 text-primary shadow-sm"
          : "border-transparent text-muted-foreground hover:border-border/60 hover:bg-secondary/40 hover:text-foreground"
      )}
    >
      {isActive && (
        <div className="absolute left-0 top-1/2 h-2/3 w-1 -translate-y-1/2 rounded-r-md bg-primary" />
      )}
      <div
        className={cn(
          "relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors duration-150",
          isActive 
            ? "bg-primary/15 text-primary"
            : "bg-secondary/50 text-muted-foreground group-hover:bg-secondary group-hover:text-primary/80"
        )}
      >
        <Icon className="h-[18px] w-[18px]" strokeWidth={2.5} />
      </div>
      <div className="min-w-0 flex-1 z-10">
        <p className={cn("truncate font-semibold tracking-tight transition-colors duration-300", isActive ? "text-primary" : "text-foreground/80 group-hover:text-foreground")}>
          {item.label}
        </p>
        <p className="truncate text-[11px] font-normal text-muted-foreground/80 transition-colors duration-300 group-hover:text-muted-foreground">{item.description}</p>
      </div>
    </NavLink>
  );
}

function SettingsSidebar({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate?: () => void }) {
  const location = useLocation();
  const { t } = useI18n();

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border/40 bg-card/60 px-5 py-5">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/15 bg-primary/10">
            <Settings className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-foreground/90">{t("nav.settings")}</h1>
            <p className="text-xs font-medium text-muted-foreground">{t("settings.subtitle")}</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="space-y-6">
          {settingsNavGroups.map((group) => {
            // Filter out admin-only items for non-admins
            const visibleItems = group.items.filter(
              (item) => !item.adminOnly || isAdmin
            );
            
            if (visibleItems.length === 0) return null;

            return (
              <div key={group.id}>
                <div className="mb-3 flex items-center gap-2 px-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
                    {group.label}
                  </p>
                  <div className="h-px flex-1 bg-border/40" />
                </div>
                <div className="space-y-1.5 px-1">
                  {visibleItems.map((item) => {
                    const isActive = location.pathname === item.path;
                    return (
                      <div key={item.id} onClick={onNavigate}>
                        <NavItem item={item} isActive={isActive} />
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>
      </ScrollArea>

      {/* Footer hint */}
      <div className="mt-auto border-t border-border/40 bg-secondary/10 px-5 py-4">
        <div className="rounded-xl border border-primary/10 bg-primary/5 p-3">
          <p className="relative z-10 text-[11.5px] font-medium leading-relaxed text-foreground/70">
            {t("settings.hint")}
          </p>
        </div>
      </div>
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
    <div className="flex h-full bg-background">
      {/* Large-screen sidebar */}
      <aside className="z-10 hidden w-[304px] shrink-0 border-r border-border/40 bg-card/50 lg:block">
        <SettingsSidebar isAdmin={isAdmin} />
      </aside>

      {/* Mobile header + sheet */}
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="shrink-0">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Открыть меню настроек</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SettingsSidebar isAdmin={isAdmin} onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>
          <div className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-primary" />
            <span className="font-semibold">{t("nav.settings")}</span>
          </div>
        </header>

        {/* Main content area */}
        <main className="relative flex-1 overflow-auto bg-background">
          <div className="relative z-0 mx-auto max-w-6xl px-4 py-8 lg:px-10 lg:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
