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

function NavItem({ item, isActive }: { item: SettingsNavItem; isActive: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      className={cn(
        "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all",
        "hover:bg-secondary/60",
        isActive
          ? "bg-secondary/80 text-foreground border-l-2 border-primary -ml-[2px] pl-[14px]"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
          isActive ? "bg-primary/10 text-primary" : "bg-secondary/50 text-muted-foreground group-hover:bg-secondary"
        )}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className={cn("truncate font-medium", isActive ? "text-foreground" : "text-foreground/80")}>
          {item.label}
        </p>
        <p className="truncate text-[11px] text-muted-foreground">{item.description}</p>
      </div>
    </NavLink>
  );
}

function SettingsSidebar({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate?: () => void }) {
  const location = useLocation();

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Settings className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-foreground">Настройки</h1>
            <p className="text-xs text-muted-foreground">Системные параметры</p>
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
                <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {group.label}
                </p>
                <div className="space-y-1">
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
      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Начинай с AI-схемы и доступов. Логирование и журнал для контроля.
        </p>
      </div>
    </div>
  );
}

export default function SettingsLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = authData?.user?.is_staff ?? false;

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <aside className="hidden w-72 shrink-0 border-r border-border bg-card lg:block">
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
            <span className="font-semibold">Настройки</span>
          </div>
        </header>

        {/* Main content area */}
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-5xl px-4 py-6 lg:px-8 lg:py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
