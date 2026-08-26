import type { QueryClient } from "@tanstack/react-query";
import type { Dispatch, SetStateAction } from "react";

import type { AssistantAction, AssistantChatMessage, AssistantChatSession } from "@/api";
import type { useToast } from "@/hooks/use-toast";
import { localize } from "@/lib/i18n";

import { replaceActionInChat } from "./chatHelpers";
import { visibleOperatorUserText } from "./operatorUserText";
import { isSshToolName, type OperatorSessionLine } from "./operatorSessionTypes";

type ToastFn = ReturnType<typeof useToast>["toast"];
type Lang = "ru" | "en" | string;

type OpenSessionDock = (opts: {
  serverId: number;
  serverName?: string;
  host?: string;
  mode?: "agent" | "live";
}) => void;

type PushSessionLine = (line: Omit<OperatorSessionLine, "id" | "at"> & { id?: string }) => void;

export type ChatOperatorHandlerCtx = {
  activeChatId: number | null;
  lang: Lang;
  toast: ToastFn;
  queryClient: QueryClient;
  messages: AssistantChatMessage[];
  pendingUserText: string | null;
  setPendingUserText: Dispatch<SetStateAction<string | null>>;
  setStreamHold: Dispatch<SetStateAction<boolean>>;
  setPendingSend: Dispatch<SetStateAction<string | null>>;
  setActionWorkingId: Dispatch<SetStateAction<number | null>>;
  openSessionDock: OpenSessionDock;
  pushSessionLine: PushSessionLine;
  refreshChat: () => Promise<void>;
  refreshTerminalChat: () => Promise<void>;
};

/** Build operator WS event handlers (same behavior as former ChatPage inline callbacks). */
export function createChatOperatorHandlers(ctx: ChatOperatorHandlerCtx) {
  const {
    activeChatId,
    lang,
    toast,
    queryClient,
    messages,
    pendingUserText,
    setPendingUserText,
    setStreamHold,
    setPendingSend,
    setActionWorkingId,
    openSessionDock,
    pushSessionLine,
    refreshChat,
    refreshTerminalChat,
  } = ctx;

  return {
    onSshSession: (payload: Record<string, unknown>) => {
      const sid = Number(payload.server_id || 0);
      if (sid <= 0) return;
      openSessionDock({
        serverId: sid,
        serverName: String(payload.server_name || ""),
        host: String(payload.host || ""),
        mode: "agent",
      });
      const cmd = String(payload.command || payload.cmd || "").trim();
      if (cmd) {
        pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
      } else {
        pushSessionLine({
          source: "system",
          kind: "note",
          text: localize(lang, "SSH-активность…", "SSH activity…"),
        });
      }
    },
    onToolResultDetail: (payload: Record<string, unknown>) => {
      // Side dock is SSH-only. Metrics / resolve / inventory must never open it
      // or dump JSON as "session opened".
      const name = String(payload.name || payload.action_type || "");
      if (!isSshToolName(name)) return;
      const sid = Number(payload.server_id || 0);
      if (sid > 0) {
        openSessionDock({
          serverId: sid,
          serverName: String(payload.server_name || ""),
          host: String(payload.host || ""),
          mode: "agent",
        });
      }
      const cmd = String(payload.command || payload.cmd || "").trim();
      if (cmd) pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
      const out = String(payload.output || "").trim();
      if (out) {
        pushSessionLine({
          source: "agent",
          kind: payload.ok === false ? "err" : "out",
          text: out.slice(0, 4000),
        });
      }
    },
    onConfirmRequired: (action: AssistantAction | { id: number }) => {
      // Inject confirm card immediately — don't wait for slow refetch
      if (action && "id" in action && action.id) {
        queryClient.setQueryData<AssistantChatSession | undefined>(
          ["assistant", "chat", activeChatId],
          (previous) => replaceActionInChat(previous, action as AssistantAction),
        );
        const input = (action as AssistantAction).input || {};
        const sid = Number((input as { server_id?: number }).server_id || 0);
        if (sid > 0 && isSshToolName(String((action as AssistantAction).action_type || ""))) {
          openSessionDock({
            serverId: sid,
            serverName: String((input as { server_name?: string }).server_name || ""),
            mode: "agent",
          });
          const cmd = String((input as { command?: string; cmd?: string }).command || (input as { cmd?: string }).cmd || "");
          if (cmd) {
            pushSessionLine({
              source: "agent",
              kind: "cmd",
              text: cmd,
            });
            pushSessionLine({
              source: "system",
              kind: "note",
              text: localize(lang, "ждёт подтверждения…", "awaiting confirm…"),
            });
          }
        }
      }
      setStreamHold(true);
      void refreshChat();
      // Keep the optimistic user row until its durable REST counterpart lands.
      // Clearing here creates a visible gap before the confirmation card/query refresh.
    },
    onActionUpdate: (action: AssistantAction) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
      if (action.status === "completed" || action.status === "failed" || action.status === "cancelled" || action.status === "running") {
        setActionWorkingId((cur) => (cur === action.id ? null : cur));
      }
      // After confirmed SSH tool — show output in dock
      if (action.status === "completed" || action.status === "failed") {
        const result = (action.result || {}) as Record<string, unknown>;
        const sid = Number(result.server_id || (action.input as { server_id?: number })?.server_id || 0);
        if (sid > 0 && isSshToolName(String(action.action_type || ""))) {
          openSessionDock({
            serverId: sid,
            serverName: String(result.server_name || ""),
            mode: "agent",
          });
          const cmd = String(
            result.command ||
              (action.input as { command?: string; cmd?: string })?.command ||
              (action.input as { cmd?: string })?.cmd ||
              "",
          );
          if (cmd) pushSessionLine({ source: "agent", kind: "cmd", text: cmd });
          const out = String(result.output || result.error || "");
          if (out) {
            pushSessionLine({
              source: "agent",
              kind: action.status === "failed" ? "err" : "out",
              text: out.slice(0, 4000),
            });
          }
        }
      }
    },
    onTurnComplete: (payload: { status?: string; actions?: AssistantAction[] }) => {
      setStreamHold(true);
      setActionWorkingId(null);
      // Merge confirm actions into cache before refetch lands
      if (payload?.actions?.length && activeChatId) {
        for (const action of payload.actions) {
          queryClient.setQueryData<AssistantChatSession | undefined>(
            ["assistant", "chat", activeChatId],
            (previous) => replaceActionInChat(previous, action),
          );
        }
      }
      void refreshTerminalChat();
      setPendingSend(null);
      // Keep the optimistic user row mounted until the matching durable REST
      // message arrives. Clearing it on the WebSocket completion event can
      // create a blank frame when the final query invalidation is still in
      // flight; the runtime reconciliation effect owns the actual handoff.
    },
    onSnapshot: (payload: {
      status?: string;
      busy?: boolean;
      assistantText?: string;
      userText?: string;
      action?: AssistantAction | null;
    }) => {
      const visibleUserText = visibleOperatorUserText(payload.userText || "");
      if (visibleUserText && !pendingUserText) {
        // User already in history after reconnect — only show optimistic if missing
        const hasUser = messages.some(
          (m) =>
            m.role === "user" &&
            visibleOperatorUserText(m.content) === visibleUserText,
        );
        if (!hasUser && payload.busy) setPendingUserText(visibleUserText);
      }
      if (payload.busy) setStreamHold(true);
      if (payload.action && "id" in payload.action && payload.action.id) {
        queryClient.setQueryData<AssistantChatSession | undefined>(
          ["assistant", "chat", activeChatId],
          (previous) => replaceActionInChat(previous, payload.action as AssistantAction),
        );
      }
      if (payload.busy || payload.status === "awaiting_confirm") {
        void refreshChat();
      } else if (
        ["done", "completed", "failed", "limit", "cancelled", "stopped", "error"].includes(
          String(payload.status || "").toLowerCase(),
        )
      ) {
        void refreshTerminalChat();
      }
    },
    onError: (message: string) => {
      toast({
        title: localize(lang, "Оператор", "Operator"),
        description: message,
        variant: "destructive",
      });
      setPendingSend(null);
      setStreamHold(false);
      // The server persists the user message before provider execution. Let the
      // shared REST handoff effect retire the optimistic row without a blank frame.
      void refreshTerminalChat();
    },
  };
}
