import { Bot, Boxes, BrainCircuit, Languages, LayoutDashboard, LogOut, PanelLeftClose, PanelLeftOpen, Server, Settings, ShieldCheck, Workflow } from "lucide-react";
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
import { localize, useI18n } from "@/lib/i18n";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";

const KUBERNETES_NAV_READY = false;

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
    { titleKey: "nav.kubernetes", url: "/kubernetes", icon: Boxes, feature: "kubernetes", ready: KUBERNETES_NAV_READY },
    { titleKey: "nav.mars", url: "/mars", icon: BrainCircuit, feature: "mars" },
    { titleKey: "nav.settings", url: "/settings", icon: Settings, feature: "settings" },
  ];

  const allowedItems = navItems.filter((item) => {
    if ("ready" in item && item.ready === false) return false;
    if (!item.feature) return true;
    if (item.feature === "studio") {
      return canAccessStudio(data?.user);
    }
    return hasFeatureAccess(data?.user, item.feature);
  });

  const roleLabel = data?.user?.is_staff ? t("nav.admin") : t("nav.operator");
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const navSections = [
    {
      id: "workspace",
      label: t("nav.workspace_label"),
      items: allowedItems.filter((item) => item.titleKey !== "nav.settings"),
    },
    {
      id: "control",
      label: localize(lang, "Управление", "Control"),
      items: allowedItems.filter((item) => item.titleKey === "nav.settings"),
    },
  ].filter((section) => section.items.length > 0);

  const handleLogout = async () => {
    await authLogout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    navigate("/login", { replace: true });
  };

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border/90 bg-sidebar">
      {/* Logo area */}
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border/80 px-3">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-sidebar-primary/20 bg-sidebar-primary/15 text-sidebar-primary shadow-[0_0_24px_hsl(var(--sidebar-primary)_/_0.08)] transition-colors hover:bg-sidebar-primary/20"
          aria-label={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
          title={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
        >
          {collapsed ? <span className="text-xs font-bold text-sidebar-primary">W</span> : <CollapseIcon className="h-4 w-4 text-sidebar-primary" />}
        </button>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-sidebar-foreground">WebTermAI</div>
            <div className="truncate text-xs text-sidebar-foreground/70">{t("nav.ops_workspace")}</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <SidebarContent className="px-3 py-4">
        {navSections.map((section) => (
          <SidebarGroup key={section.id} className={collapsed ? "mb-2" : "mb-4"}>
            {!collapsed ? (
              <div className="mb-2 px-3 text-xs font-medium uppercase tracking-[0.14em] text-sidebar-foreground/70">
                {section.label}
              </div>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu className="space-y-1">
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.titleKey}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        end={item.url === "/dashboard"}
                        className="group relative flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm text-sidebar-foreground/70 transition-all duration-150 hover:bg-sidebar-accent/80 hover:text-sidebar-foreground"
                        activeClassName="bg-sidebar-accent/95 text-sidebar-accent-foreground font-semibold shadow-[inset_0_0_0_1px_hsl(var(--sidebar-border)),0_8px_24px_hsl(var(--background)_/_0.18)] before:absolute before:left-0 before:top-1/2 before:h-6 before:w-0.5 before:-translate-y-1/2 before:rounded-r before:bg-sidebar-primary"
                        title={collapsed ? t(item.titleKey) : undefined}
                      >
                        <item.icon className="h-4 w-4 shrink-0 transition-colors" />
                        {!collapsed && <span className="truncate">{t(item.titleKey)}</span>}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="space-y-2 border-t border-sidebar-border/80 px-3 py-3">
        {!collapsed ? (
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-sidebar-border/80 bg-sidebar-accent/40 p-1 text-xs">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`min-h-9 rounded-md px-2 py-1.5 transition-colors ${lang === "en" ? "bg-sidebar text-sidebar-primary shadow-sm" : "text-sidebar-foreground/60 hover:text-sidebar-foreground"}`}
              aria-pressed={lang === "en"}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLang("ru")}
              className={`min-h-9 rounded-md px-2 py-1.5 transition-colors ${lang === "ru" ? "bg-sidebar text-sidebar-primary shadow-sm" : "text-sidebar-foreground/60 hover:text-sidebar-foreground"}`}
              aria-pressed={lang === "ru"}
            >
              RU
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setLang(lang === "ru" ? "en" : "ru")}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
            aria-label={localize(lang, "Переключить язык", "Switch language")}
            title={localize(lang, "Переключить язык", "Switch language")}
          >
            <Languages className="h-4 w-4" />
          </button>
        )}

        <div className={collapsed ? "flex flex-col items-center gap-2" : "flex items-center gap-2.5"}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-sidebar-primary/20 bg-primary/15 text-xs font-bold text-primary">
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-sidebar-foreground truncate">{data?.user?.username || "user"}</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-sidebar-foreground/70">
                <ShieldCheck className="h-2.5 w-2.5" />
                {roleLabel}
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              type="button"
              className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
              title={t("nav.signout")}
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          )}
          {collapsed && (
            <button
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-lg text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-destructive"
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
