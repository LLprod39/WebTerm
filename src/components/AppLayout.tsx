import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Outlet, useLocation, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const immersiveMeta: Array<{ match: RegExp; title: string; backTo: string; hideHeader?: boolean }> = [
  { match: /^\/servers\/hub$/, title: "Terminal Hub", backTo: "/servers" },
  { match: /^\/servers\/\d+\/terminal$/, title: "Terminal", backTo: "/servers" },
  { match: /^\/servers\/\d+\/rdp$/, title: "RDP", backTo: "/servers" },
  { match: /^\/agents\/run\/\d+$/, title: "Agent Run", backTo: "/agents" },
  { match: /^\/studio\/pipeline\/(?:new|\d+)$/, title: "Pipeline Editor", backTo: "/studio", hideHeader: true },
];

export default function AppLayout() {
  const location = useLocation();
  const immersive = immersiveMeta.find(({ match }) => match.test(location.pathname));

  if (immersive) {
    return (
      <SidebarProvider>
        <div className="flex min-h-screen w-full bg-background">
          <AppSidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            {!immersive.hideHeader && (
              <header className="flex h-10 items-center gap-3 border-b border-border px-3 bg-card/40">
                <SidebarTrigger className="text-muted-foreground hover:text-foreground h-6 w-6" />
                <Link
                  to={immersive.backTo}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  <ArrowLeft className="h-3 w-3" />
                  Back
                </Link>
                <span className="text-xs font-medium text-foreground">{immersive.title}</span>
              </header>
            )}
            <main className="min-h-0 flex-1 overflow-auto">
              <Outlet />
            </main>
          </div>
        </div>
      </SidebarProvider>
    );
  }

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full bg-background">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-h-0 flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
