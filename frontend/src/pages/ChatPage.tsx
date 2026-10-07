import { useEffect, useState } from "react";

import {
  Drawer,
  DrawerContent,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

import { ChatContextRail } from "./chat-page/ChatContextRail";
import { ChatComposerForm } from "./chat-page/ChatComposerForm";
import { ChatMessagesPane } from "./chat-page/ChatMessagesPane";
import { ChatThreadSidebar } from "./chat-page/ChatThreadSidebar";
import { useChatPageController } from "./chat-page/useChatPageController";
import "./chat-page/chatBoardUi.css";

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

const HISTORY_COLLAPSED_KEY = "wt.chat.historyCollapsed";

export default function ChatPage() {
  const c = useChatPageController();
  const isLg = useIsLg();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(HISTORY_COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(HISTORY_COLLAPSED_KEY, historyCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [historyCollapsed]);

  // On /chat, Ctrl/Cmd+B toggles chat history (capture steals AppSidebar shortcut).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "b" || !(event.metaKey || event.ctrlKey) || event.altKey) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (window.matchMedia("(min-width: 1024px)").matches) {
        setHistoryCollapsed((value) => !value);
      } else {
        setHistoryOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  const railOpen = c.contextRail.open;
  const railTab = c.contextRail.tab;
  const showDesktopRail = railOpen && isLg;
  const showMobileRail = railOpen && !isLg;

  const closeRail = () => {
    if (railTab === "terminal") c.closeSessionDock();
    else c.closeContextRail();
  };

  const conversation = (
    <section
      data-testid="chat-conversation"
      className="relative z-[1] flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
    >
      <ChatMessagesPane
        c={c}
        onOpenHistory={() => setHistoryOpen(true)}
        historyCollapsed={historyCollapsed}
        onToggleHistoryCollapsed={() => setHistoryCollapsed((value) => !value)}
      />
      <ChatComposerForm c={c} />
    </section>
  );

  const railProps = {
    tab: railTab,
    onTabChange: (tab: "tasks" | "terminal" | "details") => c.openContextRail(tab),
    onClose: closeRail,
    plan: c.activePlan,
    turnActive: c.isBusy,
    continueAvailable: Boolean(c.operatorWs.planContinueAvailable),
    onContinuePlan: () => {
      c.dispatchMessage(
        c.lang === "ru" ? "Продолжи план" : "Continue the plan",
        { skipPins: true },
      );
    },
    session: c.sessionDock,
    actionDetails: c.actionDetails,
    onModeChange: (mode: "agent" | "live") => c.setSessionDock((s) => ({ ...s, mode })),
    onHumanCommand: c.handleHumanCommand,
    onOpenTerminalFromDetails: c.sessionDock.open && c.sessionDock.serverId
      ? () => c.openContextRail("terminal")
      : undefined,
  };

  return (
    // Full-height shell flush with AppSidebar: history | conversation | optional rail.
    <div className="wt-chat-shell flex h-full min-h-0 w-full overflow-hidden text-foreground">
      <ChatThreadSidebar
        c={c}
        collapsed={historyCollapsed}
        onExpand={() => setHistoryCollapsed(false)}
      />

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" className="w-[min(22rem,88vw)] p-0 lg:hidden">
          <SheetTitle className="sr-only">
            {c.lang === "ru" ? "История чатов" : "Chat history"}
          </SheetTitle>
          <ChatThreadSidebar c={c} mobile onNavigate={() => setHistoryOpen(false)} />
        </SheetContent>
      </Sheet>

      <Drawer
        open={showMobileRail}
        onOpenChange={(open) => {
          if (!open) closeRail();
        }}
        shouldScaleBackground={false}
      >
        <DrawerContent className="h-[min(85dvh,40rem)] p-0">
          <DrawerTitle className="sr-only">
            {c.lang === "ru" ? "Контекст" : "Context"}
          </DrawerTitle>
          <div className="min-h-0 flex-1 overflow-hidden">
            <ChatContextRail {...railProps} embedded />
          </div>
        </DrawerContent>
      </Drawer>

      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {showDesktopRail ? (
          <ResizablePanelGroup direction="horizontal" className="h-full w-full">
            <ResizablePanel defaultSize={70} minSize={45} className="min-w-0">
              {conversation}
            </ResizablePanel>
            <ResizableHandle withHandle className="opacity-60" />
            <ResizablePanel defaultSize={30} minSize={18} maxSize={42} className="min-w-[18rem] border-s border-border/60">
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
