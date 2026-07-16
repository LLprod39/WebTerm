import { Languages, LogOut, PanelLeftClose, PanelLeftOpen, ShieldCheck } from "lucide-react";
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
import { NavIcons } from "@/lib/app-icons";
import { prefetchRouteForPath } from "@/lib/route-prefetch";
import { cn } from "@/lib/utils";

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
    { titleKey: "nav.dashboard", url: "/dashboard", icon: NavIcons.dashboard, feature: "dashboard" },
    { titleKey: "nav.servers", url: "/servers", icon: NavIcons.servers, feature: "servers" },
    { titleKey: "nav.agents", url: "/agents", icon: NavIcons.agents, feature: "agents" },
    { titleKey: "nav.chat", url: "/chat", icon: NavIcons.chat, feature: "orchestrator", ready: CHAT_NAV_READY },
    { titleKey: "nav.studio", url: "/studio", icon: NavIcons.studio, feature: "studio" },
    { titleKey: "nav.kubernetes", url: "/kubernetes", icon: NavIcons.kubernetes, feature: "kubernetes", ready: kubernetesNavReady },
    { titleKey: "nav.mars", url: "/mars", icon: NavIcons.mars, feature: "mars" },
    { titleKey: "nav.insights", url: "/monitoring/insights", icon: NavIcons.insights, feature: "dashboard", staffOnly: true },
    { titleKey: "nav.settings", url: "/settings", icon: NavIcons.settings, feature: "settings" },
  ];

  const allowedItems = navItems.filter((item) => {
    if ("ready" in item && item.ready === false) return false;
    if ("staffOnly" in item && item.staffOnly && !isStaff) return false;
    if (!item.feature) return true;
    if (item.feature === "studio") {
      return canAccessStudio(data?.user);
    }
    return hasFeatureAccess(data?.user, item.feature);
  });

  const roleLabel = data?.user?.is_staff ? t("nav.admin") : t("nav.operator");
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const controlKeys = ["nav.insights", "nav.settings"];
  const navSections = [
    {
      id: "workspace",
      label: t("nav.workspace_label"),
      items: allowedItems.filter((item) => !controlKeys.includes(item.titleKey)),
    },
    {
      id: "control",
      label: localize(lang, "Управление", "Control"),
      items: allowedItems.filter((item) => controlKeys.includes(item.titleKey)),
    },
  ].filter((section) => section.items.length > 0);

  const handleLogout = async () => {
    await authLogout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    navigate("/login", { replace: true });
  };

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border/80 bg-sidebar">
      {/* Logo — compact, no heavy chrome */}
      <div className="flex h-12 items-center gap-2.5 border-b border-sidebar-border/70 px-2.5">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/80 hover:text-sidebar-foreground"
          aria-label={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
          title={collapsed ? localize(lang, "Развернуть меню", "Expand sidebar") : localize(lang, "Свернуть меню", "Collapse sidebar")}
        >
          {collapsed ? (
            <span className="text-[11px] font-semibold tracking-tight text-sidebar-primary">W</span>
          ) : (
            <CollapseIcon className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
        </button>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold tracking-tight text-sidebar-foreground">
              WebTerm
            </div>
            <div className="truncate text-[10px] uppercase tracking-[0.14em] text-sidebar-foreground/45">
              {t("nav.ops_workspace")}
            </div>
          </div>
        )}
      </div>

      {/* Navigation — same language as Settings sidebar: icon tile + label row */}
      <SidebarContent className="px-2 py-3">
        {navSections.map((section) => (
          <SidebarGroup key={section.id} className={collapsed ? "mb-2" : "mb-3.5"}>
            {!collapsed ? (
              <div className="mb-1.5 px-2 text-[10px] font-medium uppercase tracking-[0.14em] text-sidebar-foreground/45">
                {section.label}
              </div>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu className="space-y-0.5">
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.titleKey}>
                    <SidebarMenuButton asChild size="sm" className="h-auto p-0 hover:bg-transparent data-[active=true]:bg-transparent">
                      <NavLink
                        to={item.url}
                        end={item.url === "/dashboard"}
                        onMouseEnter={() => prefetchRouteForPath(item.url)}
                        onFocus={() => prefetchRouteForPath(item.url)}
                        className={cn(
                          "group flex min-h-10 items-center gap-2.5 rounded-sm border border-transparent px-2 py-1.5 text-[13px] transition-colors",
                          "text-sidebar-foreground/60",
                          // quiet hover — text only, no fill/border flash
                          "hover:text-sidebar-foreground",
                          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-ring",
                          collapsed && "justify-center px-1.5",
                        )}
                        activeClassName={cn(
                          "border-primary/40 bg-primary/12 text-sidebar-foreground shadow-elev-1",
                          "[&_.nav-icon-tile]:border-primary/35 [&_.nav-icon-tile]:bg-primary/15 [&_.nav-icon-tile]:text-primary",
                        )}
                        title={collapsed ? t(item.titleKey) : undefined}
                      >
                        <span
                          className={cn(
                            "nav-icon-tile flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border",
                            "border-sidebar-border/80 bg-sidebar-accent/30 text-sidebar-foreground/65",
                          )}
                        >
                          <item.icon className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
                        </span>
                        {!collapsed && (
                          <span className="min-w-0 truncate font-medium leading-5 tracking-tight">
                            {t(item.titleKey)}
                          </span>
                        )}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      {/* Footer — quiet controls */}
      <SidebarFooter className="space-y-2 border-t border-sidebar-border/70 px-2.5 py-2.5">
        {!collapsed ? (
          <div className="flex items-center gap-0.5 rounded-md bg-sidebar-accent/25 p-0.5 text-[10px] font-medium uppercase tracking-wider">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={cn(
                "min-h-7 flex-1 rounded px-2 py-1 transition-colors",
                lang === "en"
                  ? "bg-sidebar-accent text-sidebar-foreground shadow-sm"
                  : "text-sidebar-foreground/45 hover:text-sidebar-foreground",
              )}
              aria-pressed={lang === "en"}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLang("ru")}
              className={cn(
                "min-h-7 flex-1 rounded px-2 py-1 transition-colors",
                lang === "ru"
                  ? "bg-sidebar-accent text-sidebar-foreground shadow-sm"
                  : "text-sidebar-foreground/45 hover:text-sidebar-foreground",
              )}
              aria-pressed={lang === "ru"}
            >
              RU
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setLang(lang === "ru" ? "en" : "ru")}
            className="mx-auto flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/55 transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-foreground"
            aria-label={localize(lang, "Переключить язык", "Switch language")}
            title={localize(lang, "Переключить язык", "Switch language")}
          >
            <Languages className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        )}

        <div className={collapsed ? "flex flex-col items-center gap-1.5" : "flex items-center gap-2"}>
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sidebar-accent/60 text-[11px] font-semibold text-sidebar-foreground/80">
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-medium tracking-tight text-sidebar-foreground">
                {data?.user?.username || "user"}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-[10px] uppercase tracking-[0.12em] text-sidebar-foreground/40">
                <ShieldCheck className="h-2.5 w-2.5" strokeWidth={1.5} />
                {roleLabel}
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              type="button"
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-sidebar-foreground/40 transition-colors hover:bg-sidebar-accent/70 hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
              title={t("nav.signout")}
            >
              <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          )}
          {collapsed && (
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/40 transition-colors hover:bg-sidebar-accent/70 hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
              title={t("nav.signout")}
            >
              <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
