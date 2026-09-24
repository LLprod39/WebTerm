import { useEffect, useState } from "react";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

import { ChatContextRail } from "./chat-page/ChatContextRail";
import { ChatComposerForm } from "./chat-page/ChatComposerForm";
import { ChatMessagesPane } from "./chat-page/ChatMessagesPane";
import { ChatThreadSidebar } from "./chat-page/ChatThreadSidebar";
import { useChatPageController } from "./chat-page/useChatPageController";

/** Matches Tailwind `lg` — desktop split vs mobile sheet for the context rail. */
function useIsLg() {
  const [isLg, setIsLg] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(min-width: 1024px)").matches : true,
  );
  useEffect(() => {
    const mql = window.matchMedia("(min-width: 1024px)");
    const onChange = () => setIsLg(mql.matches);
    mql.addEventListener("change", onChange);
    setIsLg(mql.matches);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return isLg;
}

export default function ChatPage() {
  const c = useChatPageController();
  const isLg = useIsLg();
  const [historyOpen, setHistoryOpen] = useState(false);

  const railOpen = c.contextRail.open;
  const railTab = c.contextRail.tab;
  const showDesktopRail = railOpen && isLg;
  const showMobileRail = railOpen && !isLg;

  const closeRail = () => {
    if (railTab === "terminal") c.closeSessionDock();
    else c.closeContextRail();
  };

  const conversation = (
    <section className="relative z-[1] flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <ChatMessagesPane c={c} onOpenHistory={() => setHistoryOpen(true)} />
      <ChatComposerForm c={c} />
    </section>
  );

  const railProps = {
    tab: railTab,
    onTabChange: (tab: "tasks" | "terminal" | "details") => c.openContextRail(tab),
    onClose: closeRail,
    plan: c.activePlan,
    session: c.sessionDock,
    actionDetails: c.actionDetails,
    onModeChange: (mode: "agent" | "live") => c.setSessionDock((s) => ({ ...s, mode })),
    onHumanCommand: c.handleHumanCommand,
    onOpenTerminalFromDetails: c.sessionDock.open && c.sessionDock.serverId
      ? () => c.openContextRail("terminal")
      : undefined,
  };

  return (
    // Row layout: chat list | conversation | optional single context rail.
    // Must NOT be flex-col — the sidebar with h-full would eat the full height.
    <div className="flex h-[calc(100dvh-5rem)] max-h-[calc(100dvh-5rem)] w-full overflow-hidden bg-card text-foreground">
      <ChatThreadSidebar c={c} />

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" className="w-[min(22rem,88vw)] p-0 lg:hidden">
          <SheetTitle className="sr-only">
            {c.lang === "ru" ? "История чатов" : "Chat history"}
          </SheetTitle>
          <ChatThreadSidebar c={c} mobile onNavigate={() => setHistoryOpen(false)} />
        </SheetContent>
      </Sheet>

      <Sheet open={showMobileRail} onOpenChange={(open) => { if (!open) closeRail(); }}>
        <SheetContent side="right" className="w-[min(26rem,92vw)] p-0">
          <SheetTitle className="sr-only">
            {c.lang === "ru" ? "Контекст" : "Context"}
          </SheetTitle>
          <ChatContextRail {...railProps} embedded />
        </SheetContent>
      </Sheet>

      <div className="flex h-full min-h-0 min-w-0 flex-1 overflow-hidden">
        {showDesktopRail ? (
          <ResizablePanelGroup direction="horizontal" className="h-full w-full">
            <ResizablePanel defaultSize={72} minSize={45} className="min-w-0">
              {conversation}
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={28} minSize={18} maxSize={42} className="min-w-[18rem]">
              <ChatContextRail {...railProps} />
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          conversation
        )}
      </div>
    </div>
  );
}
