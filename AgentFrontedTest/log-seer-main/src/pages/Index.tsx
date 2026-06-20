import { useState } from "react";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SidebarContent } from "@/components/report/SidebarContent";
import { TopBar } from "@/components/report/TopBar";
import { Hero } from "@/components/report/Hero";
import { KpiCards } from "@/components/report/KpiCards";
import { OverviewTab } from "@/components/report/tabs/OverviewTab";
import { EventsTab } from "@/components/report/tabs/EventsTab";
import { ArtifactsTab } from "@/components/report/tabs/ArtifactsTab";
import { AgentRunTab } from "@/components/report/tabs/AgentRunTab";
import { LayoutGrid, List, FolderArchive, Workflow } from "lucide-react";

const tabs = [
  { value: "overview", label: "Обзор", icon: LayoutGrid },
  { value: "events", label: "События", icon: List },
  { value: "artifacts", label: "Артефакты", icon: FolderArchive },
  { value: "agent", label: "Ход агента", icon: Workflow },
];

const Index = () => {
  const [mobileNav, setMobileNav] = useState(false);
  const [tab, setTab] = useState("overview");

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop full sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[220px] border-r border-sidebar-border lg:block">
        <SidebarContent />
      </aside>
      {/* Tablet icon rail */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-16 border-r border-sidebar-border md:block lg:hidden">
        <SidebarContent collapsed />
      </aside>

      {/* Mobile drawer */}
      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-[240px] border-sidebar-border bg-sidebar p-0">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* Main */}
      <div className="md:pl-16 lg:pl-[220px]">
        <TopBar onOpenMobileNav={() => setMobileNav(true)} />

        <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
          <div className="space-y-5">
            <Hero />
            <KpiCards />

            <Tabs value={tab} onValueChange={setTab} className="space-y-5">
              <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1.5 sm:w-auto">
                {tabs.map((t) => {
                  const Icon = t.icon;
                  return (
                    <TabsTrigger
                      key={t.value}
                      value={t.value}
                      className="h-10 gap-2 rounded-lg px-4 text-sm data-[state=active]:bg-secondary data-[state=active]:text-foreground data-[state=active]:shadow-none"
                    >
                      <Icon className="h-4 w-4" />
                      {t.label}
                    </TabsTrigger>
                  );
                })}
              </TabsList>

              <TabsContent value="overview" className="animate-fade-in focus-visible:outline-none">
                <OverviewTab onGoToArtifacts={() => setTab("artifacts")} />
              </TabsContent>
              <TabsContent value="events" className="animate-fade-in focus-visible:outline-none">
                <EventsTab />
              </TabsContent>
              <TabsContent value="artifacts" className="animate-fade-in focus-visible:outline-none">
                <ArtifactsTab />
              </TabsContent>
              <TabsContent value="agent" className="animate-fade-in focus-visible:outline-none">
                <AgentRunTab />
              </TabsContent>
            </Tabs>
          </div>

          <footer className="mt-10 border-t border-border pt-5 text-center text-xs text-muted-foreground">
            Отчёт сформирован автоматически • 16.06.2026, 23:12:47
          </footer>
        </main>
      </div>
    </div>
  );
};

export default Index;
