import { LayoutDashboard, Server, Settings, LogOut, Bot, Workflow, ChevronLeft } from "lucide-react";
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
    return Boolean(data?.user?.features?.[item.feature]);
  });

  const handleLogout = async () => {
    await authLogout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    navigate("/login", { replace: true });
  };

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar">
      {/* Logo area */}
      <div className="flex h-12 items-center gap-2 border-b border-sidebar-border px-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-primary/10">
          <span className="text-xs font-bold text-primary">W</span>
        </div>
        {!collapsed && (
          <span className="text-sm font-semibold text-foreground tracking-tight">
            WebTermAI
          </span>
        )}
        {!collapsed && (
          <button
            onClick={toggleSidebar}
            className="ml-auto text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Navigation */}
      <SidebarContent className="px-2 py-3">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="space-y-0.5">
              {allowedItems.map((item) => (
                <SidebarMenuItem key={item.titleKey}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.url}
                      end={item.url === "/dashboard"}
                      className="flex items-center gap-2.5 px-2.5 py-1.5 rounded text-[13px] text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors"
                      activeClassName="bg-sidebar-accent text-primary font-medium"
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
      <SidebarFooter className="border-t border-sidebar-border px-3 py-2.5">
        {!collapsed && (
          <div className="flex justify-center mb-2">
            <div className="inline-flex rounded border border-border overflow-hidden text-[10px] font-medium">
              <button
                onClick={() => setLang("en")}
                className={`px-2 py-0.5 transition-colors ${lang === "en" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              >
                EN
              </button>
              <button
                onClick={() => setLang("ru")}
                className={`px-2 py-0.5 transition-colors ${lang === "ru" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              >
                RU
              </button>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2.5">
          <div className="h-6 w-6 rounded bg-secondary flex items-center justify-center text-[10px] font-semibold text-foreground shrink-0">
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
              className="text-muted-foreground hover:text-destructive transition-colors p-0.5"
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
