import { Bot, Boxes, BrainCircuit, Languages, LayoutDashboard, LogOut, MessageSquare, PanelLeftClose, PanelLeftOpen, Server, Settings, ShieldCheck, Workflow } from "lucide-react";
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
import { authLogout, fetchAuthSession, fetchKubernetesReadiness } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { localize, useI18n } from "@/lib/i18n";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";

const CHAT_NAV_READY = false;

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
  const isStaff = Boolean(data?.user?.is_staff);
  const hasKubernetesFeature = hasFeatureAccess(data?.user, "kubernetes");
  const { data: kubernetesReadiness } = useQuery({
    queryKey: ["kubernetes", "readiness", "sidebar"],
    // Staff always get the nav entry when the feature is on; readiness only gates operators.
    queryFn: fetchKubernetesReadiness,
    enabled: hasKubernetesFeature && !isStaff,
    staleTime: 60_000,
    retry: false,
  });
  // Admins: open Kubernetes as soon as the feature is granted.
  // Operators: keep production/pilot sidebar gate (ready_for_sidebar).
  const kubernetesNavReady = isStaff || Boolean(kubernetesReadiness?.ready_for_sidebar);

  const navItems = [
    { titleKey: "nav.dashboard", url: "/dashboard", icon: LayoutDashboard, feature: "dashboard" },
    { titleKey: "nav.servers", url: "/servers", icon: Server, feature: null },
    { titleKey: "nav.agents", url: "/agents", icon: Bot, feature: "agents" },
    { titleKey: "nav.chat", url: "/chat", icon: MessageSquare, feature: "orchestrator", ready: CHAT_NAV_READY },
    { titleKey: "nav.studio", url: "/studio", icon: Workflow, feature: "studio" },
    { titleKey: "nav.kubernetes", url: "/kubernetes", icon: Boxes, feature: "kubernetes", ready: kubernetesNavReady },
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
    <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar">
      {/* Logo area */}
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-3">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-sidebar-primary/40 bg-sidebar-primary/12 text-sidebar-primary transition-colors hover:bg-sidebar-primary/20"
          aria-label={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
          title={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
        >
          {collapsed ? <span className="font-display text-xs font-bold text-sidebar-primary">W</span> : <CollapseIcon className="h-4 w-4 text-sidebar-primary" />}
        </button>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate font-display text-sm font-bold tracking-tight text-sidebar-foreground">WebTerm</div>
            <div className="truncate text-2xs uppercase tracking-[0.12em] text-sidebar-foreground/55">{t("nav.ops_workspace")}</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <SidebarContent className="px-2 py-4">
        {navSections.map((section) => (
          <SidebarGroup key={section.id} className={collapsed ? "mb-2" : "mb-4"}>
            {!collapsed ? (
              <div className="mb-2 px-3 text-2xs font-medium uppercase tracking-[0.14em] text-sidebar-foreground/50">
                {section.label}
              </div>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu className="space-y-0.5">
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.titleKey}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        end={item.url === "/dashboard"}
                        className="group relative flex min-h-10 items-center gap-2.5 rounded-sm px-3 py-2 text-xs text-sidebar-foreground/65 transition-all duration-150 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                        activeClassName="bg-primary/12 text-primary font-medium before:absolute before:left-0 before:top-1/2 before:h-5 before:w-[3px] before:-translate-y-1/2 before:bg-primary before:content-['']"
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
      <SidebarFooter className="space-y-2 border-t border-sidebar-border px-3 py-3">
        {!collapsed ? (
          <div className="grid grid-cols-2 gap-1 rounded-sm border border-sidebar-border bg-sidebar-accent/30 p-1 text-2xs uppercase tracking-wider">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`min-h-8 rounded-sm px-2 py-1.5 transition-colors ${lang === "en" ? "bg-primary text-primary-foreground" : "text-sidebar-foreground/55 hover:text-sidebar-foreground"}`}
              aria-pressed={lang === "en"}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLang("ru")}
              className={`min-h-8 rounded-sm px-2 py-1.5 transition-colors ${lang === "ru" ? "bg-primary text-primary-foreground" : "text-sidebar-foreground/55 hover:text-sidebar-foreground"}`}
              aria-pressed={lang === "ru"}
            >
              RU
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setLang(lang === "ru" ? "en" : "ru")}
            className="flex h-10 w-10 items-center justify-center rounded-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
            aria-label={localize(lang, "Переключить язык", "Switch language")}
            title={localize(lang, "Переключить язык", "Switch language")}
          >
            <Languages className="h-4 w-4" />
          </button>
        )}

        <div className={collapsed ? "flex flex-col items-center gap-2" : "flex items-center gap-2.5"}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/12 text-xs font-bold text-primary">
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="truncate text-xs font-medium text-sidebar-foreground">{data?.user?.username || "user"}</p>
              <p className="mt-0.5 flex items-center gap-1 text-2xs uppercase tracking-wider text-sidebar-foreground/55">
                <ShieldCheck className="h-2.5 w-2.5" />
                {roleLabel}
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              type="button"
              className="ml-auto flex h-9 w-9 items-center justify-center rounded-sm text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-destructive"
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
              className="flex h-10 w-10 items-center justify-center rounded-sm text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-destructive"
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
