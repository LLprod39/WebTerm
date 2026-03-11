import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Outlet, useLocation } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

const immersiveMeta: Array<{ match: RegExp; title: string; subtitle: string; backTo: string; hideHeader?: boolean }> = [
  { match: /^\/servers\/hub$/, title: "Terminal Hub", subtitle: "Multi-server terminal workspace", backTo: "/servers" },
  { match: /^\/servers\/\d+\/terminal$/, title: "Terminal", subtitle: "Full-width live server terminal", backTo: "/servers" },
  { match: /^\/servers\/\d+\/rdp$/, title: "RDP", subtitle: "Remote desktop workspace", backTo: "/servers" },
  { match: /^\/agents\/run\/\d+$/, title: "Agent Run", subtitle: "Live execution and operator review", backTo: "/agents" },
  { match: /^\/studio\/pipeline\/(?:new|\d+)$/, title: "Pipeline Editor", subtitle: "Focused pipeline workspace", backTo: "/studio", hideHeader: true },
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
            {!immersive.hideHeader ? (
              <header className="border-b border-border bg-card/60 px-4 py-3 backdrop-blur">
                <div className="flex items-center gap-4">
                  <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
                  <Link
                    to={immersive.backTo}
                    className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    <span>Back</span>
                  </Link>
                </div>
                <div className="mt-3 space-y-1">
                  <h1 className="text-lg font-semibold text-foreground">{immersive.title}</h1>
                  <p className="text-sm text-muted-foreground">{immersive.subtitle}</p>
                </div>
              </header>
            ) : null}
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
