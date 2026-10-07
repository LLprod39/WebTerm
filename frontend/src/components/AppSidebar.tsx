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
import { hasFeatureAccess } from "@/lib/featureAccess";
import {
  allowedPrimaryNavigation,
  type NavSectionId,
  type PrimaryNavigationItem,
} from "@/lib/navigation";
import { prefetchRouteForPath } from "@/lib/route-prefetch";
import { cn } from "@/lib/utils";

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
    queryFn: fetchKubernetesReadiness,
    enabled: hasKubernetesFeature && !isStaff,
    staleTime: 60_000,
    retry: false,
  });
  const kubernetesNavReady = isStaff || Boolean(kubernetesReadiness?.ready_for_sidebar);

  const allowedItems = allowedPrimaryNavigation(data?.user, { kubernetesReady: kubernetesNavReady });

  const roleLabel = data?.user?.is_staff ? t("nav.admin") : t("nav.operator");
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const expandLabel = localize(lang, "Развернуть меню", "Expand sidebar");
  const collapseLabel = localize(lang, "Свернуть меню", "Collapse sidebar");

  const navSections: Array<{ id: NavSectionId; label: string; items: PrimaryNavigationItem[] }> = [
    { id: "dashboard", label: t("nav.section_dashboard"), items: allowedItems.filter((item) => item.section === "dashboard") },
    { id: "infrastructure", label: t("nav.section_infrastructure"), items: allowedItems.filter((item) => item.section === "infrastructure") },
    { id: "automation", label: t("nav.section_automation"), items: allowedItems.filter((item) => item.section === "automation") },
    { id: "extensions", label: t("nav.section_extensions"), items: allowedItems.filter((item) => item.section === "extensions") },
    { id: "administration", label: t("nav.section_administration"), items: allowedItems.filter((item) => item.section === "administration") },
  ].filter((section): section is { id: NavSectionId; label: string; items: PrimaryNavigationItem[] } => section.items.length > 0);

  const handleLogout = async () => {
    await authLogout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    navigate("/login", { replace: true });
  };

  return (
    <Sidebar
      data-ui-slot="app-sidebar"
      collapsible="icon"
      className="border-r border-sidebar-border/80 bg-sidebar"
    >
      {/* Stable brand row: logo left, title (expanded), toggle right — same slots both states. */}
      <div
        data-ui-slot="sidebar-brand"
        className="flex h-12 shrink-0 items-center gap-1 border-b border-sidebar-border/70 px-1.5"
      >
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[13px] font-semibold tracking-tight text-sidebar-primary"
          aria-hidden
        >
          W
        </span>
        <div
          className={cn(
            "min-w-0 flex-1 overflow-hidden",
            collapsed ? "pointer-events-none w-0 flex-none opacity-0" : "opacity-100",
          )}
        >
          <div className="truncate text-[13px] font-semibold tracking-tight text-sidebar-foreground">
            WebTerm
          </div>
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/80 hover:text-sidebar-foreground"
          aria-label={collapsed ? expandLabel : collapseLabel}
          title={collapsed ? expandLabel : collapseLabel}
        >
          <CollapseIcon className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </div>

      <SidebarContent
        data-ui-slot="sidebar-navigation"
        className={cn(
          "gap-0 overflow-x-hidden",
          collapsed ? "items-center px-0 py-1.5" : "px-2 py-2",
        )}
      >
        {navSections.map((section, sectionIndex) => {
          // Hide only when a solo item duplicates the section title (e.g. Панель / Панель).
          const soloDuplicatesSection =
            section.items.length === 1 &&
            t(section.items[0].titleKey).localeCompare(section.label, undefined, {
              sensitivity: "accent",
            }) === 0;
          const showSectionLabel = !collapsed && !soloDuplicatesSection;

          return (
            <SidebarGroup
              key={section.id}
              data-testid={`nav-section-${section.id}`}
              className={cn(
                "p-0",
                collapsed
                  ? cn(
                      "mb-0 w-full",
                      sectionIndex > 0 && "mt-1.5 border-t border-sidebar-border/80 pt-1.5",
                    )
                  : cn("mb-1", sectionIndex > 0 && "mt-1"),
              )}
            >
              {showSectionLabel ? (
                <div className="mb-0.5 px-2 text-[11px] font-medium text-sidebar-foreground/55">
                  {section.label}
                </div>
              ) : null}
              <SidebarGroupContent>
                <SidebarMenu
                  className={cn(
                    collapsed ? "items-center gap-0.5" : "gap-0.5",
                  )}
                >
                  {section.items.map((item) => {
                    const label = t(item.titleKey);
                    return (
                      <SidebarMenuItem
                        key={item.titleKey}
                        className={collapsed ? "flex w-full justify-center" : undefined}
                      >
                        <SidebarMenuButton
                          asChild
                          size="sm"
                          tooltip={label}
                          className={cn(
                            "h-auto p-0 hover:bg-transparent data-[active=true]:bg-transparent",
                            // Keep the hit/highlight tile square inside the icon rail (never full-width).
                            collapsed &&
                              "group-data-[collapsible=icon]:!size-8 group-data-[collapsible=icon]:!min-w-0 group-data-[collapsible=icon]:!max-w-8 group-data-[collapsible=icon]:!p-0",
                          )}
                        >
                          <NavLink
                            data-ui-slot="sidebar-link"
                            to={item.path}
                            end={item.path === "/dashboard"}
                            onMouseEnter={() => prefetchRouteForPath(item.path)}
                            onFocus={() => prefetchRouteForPath(item.path)}
                            aria-label={label}
                            className={cn(
                              "flex items-center border border-transparent text-[13px] transition-colors duration-150",
                              "text-sidebar-foreground/85",
                              "hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                              collapsed
                                ? "h-8 w-8 justify-center rounded-md p-0"
                                : "min-h-8 w-full justify-start gap-2 rounded-md px-2 py-1.5",
                            )}
                            activeClassName={cn(
                              "border-transparent bg-sidebar-accent text-sidebar-foreground",
                              "hover:bg-sidebar-accent hover:text-sidebar-foreground",
                              collapsed && "bg-sidebar-accent",
                            )}
                          >
                            <span
                              className={cn(
                                "nav-icon-tile flex shrink-0 items-center justify-center",
                                collapsed ? "h-4 w-4" : "h-4 w-4",
                              )}
                            >
                              <item.icon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
                            </span>
                            {!collapsed ? (
                              <span className="min-w-0 truncate font-medium leading-5 tracking-tight">
                                {label}
                              </span>
                            ) : null}
                          </NavLink>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          );
        })}
      </SidebarContent>

      <SidebarFooter
        data-ui-slot="sidebar-footer"
        className={cn(
          "border-t border-sidebar-border/70",
          collapsed ? "items-center gap-1 px-0 py-2" : "gap-1.5 px-2 py-2",
        )}
      >
        {!collapsed ? (
          <div className="flex items-center gap-0.5 rounded-md bg-sidebar-accent/25 p-0.5 text-[11px] font-medium">
            <button
              type="button"
              onClick={() => setLang("en")}
              className={cn(
                "min-h-7 flex-1 rounded px-2 py-1 transition-colors",
                lang === "en"
                  ? "bg-sidebar-accent text-sidebar-foreground shadow-sm"
                  : "text-sidebar-foreground/70 hover:text-sidebar-foreground",
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
                  : "text-sidebar-foreground/70 hover:text-sidebar-foreground",
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
            className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-foreground"
            aria-label={localize(lang, "Переключить язык", "Switch language")}
            title={localize(lang, "Переключить язык", "Switch language")}
          >
            <Languages className="h-4 w-4" strokeWidth={1.5} />
          </button>
        )}

        <div className={collapsed ? "flex flex-col items-center gap-1" : "flex items-center gap-2"}>
          <div
            className={cn(
              "flex shrink-0 items-center justify-center rounded-full bg-sidebar-accent/60 font-semibold text-sidebar-foreground/80",
              collapsed ? "h-8 w-8 text-xs" : "h-7 w-7 text-[11px]",
            )}
          >
            {(data?.user?.username || "U").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed ? (
            <>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-medium tracking-tight text-sidebar-foreground">
                  {data?.user?.username || "user"}
                </p>
                <p className="mt-0.5 flex items-center gap-1 text-[11px] text-sidebar-foreground/55">
                  <ShieldCheck className="h-2.5 w-2.5" strokeWidth={1.5} />
                  {roleLabel}
                </p>
              </div>
              <button
                type="button"
                className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/70 hover:text-destructive"
                aria-label={t("nav.signout")}
                onClick={handleLogout}
                title={t("nav.signout")}
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </>
          ) : (
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/70 hover:text-destructive"
              aria-label={t("nav.signout")}
              onClick={handleLogout}
              title={t("nav.signout")}
            >
              <LogOut className="h-4 w-4" strokeWidth={1.5} />
            </button>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
