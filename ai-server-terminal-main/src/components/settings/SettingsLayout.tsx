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
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-300 overflow-hidden",
        isActive
          ? "bg-primary/10 text-primary shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]"
          : "text-muted-foreground hover:bg-secondary/40 hover:text-foreground hover:shadow-sm"
      )}
    >
      {isActive && (
        <div className="absolute left-0 top-1/2 -translate-y-1/2 h-2/3 w-1 bg-primary rounded-r-md shadow-[0_0_8px_rgba(var(--primary),0.5)]" />
      )}
      <div
        className={cn(
          "relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all duration-300",
          isActive 
            ? "bg-primary/20 text-primary shadow-inner" 
            : "bg-secondary/50 text-muted-foreground group-hover:bg-secondary group-hover:scale-105 group-hover:text-primary/80"
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
      {/* Subtle hover background gradient glow */}
      {!isActive && (
        <div className="absolute inset-0 z-0 bg-gradient-to-r from-transparent via-primary/5 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      )}
    </NavLink>
  );
}

function SettingsSidebar({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate?: () => void }) {
  const location = useLocation();

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border/40 bg-gradient-to-b from-secondary/30 to-transparent px-5 py-6 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 shadow-inner border border-primary/10">
            <Settings className="h-6 w-6 text-primary drop-shadow-[0_0_8px_rgba(var(--primary),0.5)] animate-pulse-slow" />
            <div className="absolute inset-0 rounded-2xl bg-primary/10 blur-xl -z-10" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-foreground/90">Настройки</h1>
            <p className="text-xs font-medium text-muted-foreground">Системные параметры</p>
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
              <div key={group.id} className="animate-in fade-in slide-in-from-left-4 duration-500 fill-mode-both" style={{ animationDelay: `${group.id === "core" ? 50 : group.id === "access" ? 150 : 250}ms` }}>
                <div className="mb-3 flex items-center gap-2 px-1">
                  <div className="h-px flex-1 bg-gradient-to-r from-border/0 via-border/50 to-border/0" />
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
                    {group.label}
                  </p>
                  <div className="h-px flex-1 bg-gradient-to-r from-border/50 to-border/0" />
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
      <div className="mt-auto border-t border-border/40 bg-secondary/10 px-5 py-4 backdrop-blur-sm">
        <div className="relative rounded-xl overflow-hidden p-3 border border-primary/10 bg-primary/5">
          <div className="absolute top-0 right-0 -mt-2 -mr-2 h-8 w-8 rounded-full bg-primary/20 blur-xl" />
          <p className="relative z-10 text-[11.5px] font-medium leading-relaxed text-foreground/70">
            Начинай с AI-схемы и доступов. Логирование и журнал для контроля.
          </p>
        </div>
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
    <div className="flex h-full bg-gradient-to-br from-background via-background to-secondary/20">
      {/* Desktop sidebar */}
      <aside className="hidden w-[320px] shrink-0 border-r border-border/30 bg-card/40 backdrop-blur-3xl shadow-[4px_0_24px_rgba(0,0,0,0.02)] lg:block z-10">
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
        <main className="flex-1 overflow-auto bg-background/50 relative">
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl -z-10 pointer-events-none" />
          <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl -z-10 mt-20 pointer-events-none" />
          
          <div className="mx-auto max-w-6xl px-4 py-8 lg:px-10 lg:py-10 relative z-0 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
