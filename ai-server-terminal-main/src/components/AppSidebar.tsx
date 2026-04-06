import { LayoutDashboard, Server, Settings, LogOut, Bot, Workflow, ChevronLeft, ChevronRight } from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useNavigate } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";
import { authLogout, fetchAuthSession } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/lib/i18n";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";

export function AppSidebar() {
  const { state, toggleSidebar } = useSidebar();
  const collapsed = state === "collapsed";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { lang, setLang, t } = useI18n();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  const navItems = [
    { titleKey: "nav.dashboard", url: "/dashboard", icon: LayoutDashboard, feature: "dashboard" },
    { titleKey: "nav.servers", url: "/servers", icon: Server, feature: null },
    { titleKey: "nav.agents", url: "/agents", icon: Bot, feature: "agents" },
    { titleKey: "nav.studio", url: "/studio", icon: Workflow, feature: "studio" },
    { titleKey: "nav.settings", url: "/settings", icon: Settings, feature: "settings" },
  ];

  const allowedItems = navItems.filter((item) => {
    if (!item.feature) return true;
    if (item.feature === "studio") {
      return canAccessStudio(data?.user);
    }
    return hasFeatureAccess(data?.user, item.feature);
  });

  const handleLogout = async () => {
    await authLogout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    navigate("/login", { replace: true });
  };

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar/95">
      {/* Logo area */}
      <div className="flex h-14 items-center gap-3 border-b border-sidebar-border/80 px-4">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10 transition-colors hover:bg-primary/15"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className="text-xs font-bold text-primary">W</span>
        </button>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight text-foreground">
            WebTermAI
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="ml-auto text-muted-foreground hover:text-foreground transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Navigation */}
      <SidebarContent className="px-3 py-4">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="space-y-1">
              {allowedItems.map((item) => (
                <SidebarMenuItem key={item.titleKey}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.url}
                      end={item.url === "/dashboard"}
                      className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      activeClassName="bg-sidebar-accent text-foreground font-medium"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{t(item.titleKey)}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="border-t border-sidebar-border/80 px-4 py-3">
        {!collapsed && (
          <div className="mb-2 flex justify-center">
            <div className="inline-flex overflow-hidden rounded-xl border border-border/70 bg-secondary/40 text-[10px] font-medium">
              <button
                onClick={() => setLang("en")}
                className={`px-2.5 py-1 transition-colors ${lang === "en" ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                EN
              </button>
              <button
                onClick={() => setLang("ru")}
                className={`px-2.5 py-1 transition-colors ${lang === "ru" ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                RU
              </button>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2.5 rounded-xl bg-secondary/35 px-2 py-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-secondary text-[10px] font-semibold text-foreground">
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">{data?.user?.username || "user"}</p>
              <p className="text-[10px] text-muted-foreground leading-tight">
                {data?.user?.is_staff ? t("nav.admin") : t("nav.operator")}
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              className="p-0.5 text-muted-foreground transition-colors hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
