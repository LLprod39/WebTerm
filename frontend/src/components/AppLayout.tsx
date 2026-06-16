import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Outlet, useLocation, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { localize, useI18n } from "@/lib/i18n";

const immersiveMeta: Array<{ match: RegExp; title: string; backTo: string; hideHeader?: boolean }> = [
  { match: /^\/servers\/hub$/, title: "Terminal Hub", backTo: "/servers", hideHeader: true },
  { match: /^\/servers\/\d+\/terminal$/, title: "Terminal", backTo: "/servers", hideHeader: true },
  { match: /^\/agents\/run\/\d+$/, title: "Agent Run", backTo: "/agents" },
  { match: /^\/studio\/pipeline\/(?:new|\d+)$/, title: "Pipeline Editor", backTo: "/studio", hideHeader: true },
];

export default function AppLayout() {
  const location = useLocation();
  const { lang } = useI18n();
  const immersive = immersiveMeta.find(({ match }) => match.test(location.pathname));
  const openNavigationLabel = localize(lang, "Открыть навигацию", "Open navigation");
  const mobileSidebarTrigger = (
    <div className="pointer-events-none fixed left-4 top-4 z-40 md:hidden">
      <SidebarTrigger
        className="pointer-events-auto h-11 w-11 rounded-xl border border-border bg-card/95 text-foreground shadow-lg shadow-background/30"
        aria-label={openNavigationLabel}
        title={openNavigationLabel}
      />
    </div>
  );

  if (immersive) {
    return (
      <SidebarProvider>
        {mobileSidebarTrigger}
        <div className="app-shell-bg flex h-screen min-h-0 w-full overflow-hidden">
          <AppSidebar />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {!immersive.hideHeader && (
              <header className="flex h-12 items-center gap-3 border-b border-border/70 bg-card/75 px-3 backdrop-blur">
                <SidebarTrigger className="h-9 w-9 text-muted-foreground hover:text-foreground" />
                <Link
                  to={immersive.backTo}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                >
                  <ArrowLeft className="h-3 w-3" />
                  Back
                </Link>
                <span className="text-xs font-medium text-foreground">{immersive.title}</span>
              </header>
            )}
            <main className="min-h-0 flex-1 overflow-hidden pt-16 animate-in fade-in duration-200 md:pt-0">
              <Outlet />
            </main>
          </div>
        </div>
      </SidebarProvider>
    );
  }

  return (
    <SidebarProvider>
      {mobileSidebarTrigger}
      <div className="app-shell-bg flex min-h-screen w-full">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-h-0 flex-1 overflow-auto pt-16 animate-in fade-in duration-200 md:pt-0">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
