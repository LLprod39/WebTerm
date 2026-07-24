import { OperatorSessionDock } from "./chat-page/OperatorSessionDock";
import { PlanTasksPanel } from "./chat-page/PlanTasksPanel";
import { ChatComposerForm } from "./chat-page/ChatComposerForm";
import { ChatMessagesPane } from "./chat-page/ChatMessagesPane";
import { ChatThreadSidebar } from "./chat-page/ChatThreadSidebar";
import { useChatPageController } from "./chat-page/useChatPageController";

export default function ChatPage() {
  const c = useChatPageController();

  return (
    // Row layout: chat list | conversation. Must NOT be flex-col — the sidebar
    // with h-full would eat the full height and hide messages + composer.
    <div className="flex h-[calc(100dvh-5rem)] max-h-[calc(100dvh-5rem)] w-full overflow-hidden bg-card text-foreground">
      <ChatThreadSidebar c={c} />

      {/* ── Main conversation column ── */}
      <section className="relative z-[1] flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <ChatMessagesPane c={c} />
        <ChatComposerForm c={c} />
      </section>

      <OperatorSessionDock
        session={c.sessionDock}
        onClose={() => c.setSessionDock((s) => ({ ...s, open: false }))}
        onModeChange={(mode) => c.setSessionDock((s) => ({ ...s, mode }))}
        onHumanCommand={c.handleHumanCommand}
      />

      <PlanTasksPanel
        plan={c.activePlan}
        open={c.tasksPanelOpen}
        onClose={() => c.setTasksPanelOpen(false)}
      />
    </div>
  );
}
