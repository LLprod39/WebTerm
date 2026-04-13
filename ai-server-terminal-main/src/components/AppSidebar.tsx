import { LayoutDashboard, Server, Settings, LogOut, Bot, Workflow, MoreVertical } from "lucide-react";
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
    <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar">
      {/* Logo area */}
      <div className="flex h-14 items-center gap-3 border-b border-sidebar-border px-4">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary/10 transition-colors hover:bg-sidebar-primary/20"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className="text-xs font-bold text-sidebar-primary">W</span>
        </button>
        {!collapsed && (
          <span className="text-sm font-semibold text-sidebar-foreground">
            WebTermAI
          </span>
        )}
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
                      className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
                      activeClassName="bg-sidebar-accent text-sidebar-accent-foreground font-medium"
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
      <SidebarFooter className="border-t border-sidebar-border px-3 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-accent text-xs font-semibold text-sidebar-accent-foreground">
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-sidebar-foreground truncate">{data?.user?.username || "user"}</p>
            </div>
          )}
          {!collapsed && (
            <button
              className="p-1.5 text-sidebar-foreground transition-colors hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
              title={t("nav.signout")}
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
