import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { fetchAssistantChat } from "@/api/assistant-chat";
import { localize, useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";

import {
  listOperatorBackgroundWatches,
  previewOperatorReply,
  unwatchOperatorChat,
} from "./operatorBackgroundWatch";

const POLL_MS = 2500;

/**
 * When the user leaves /chat while an operator turn is still running, poll the
 * watched chats and surface a short bottom toast with the reply preview.
 */
export function OperatorBackgroundNotifier() {
  const location = useLocation();
  const navigate = useNavigate();
  const { lang } = useI18n();
  const onChatRoute = location.pathname === "/chat" || location.pathname.startsWith("/chat/");
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (onChatRoute) return;

    let cancelled = false;

    const tick = async () => {
      if (cancelled || inFlightRef.current) return;
      const watches = listOperatorBackgroundWatches();
      if (!watches.length) return;
      inFlightRef.current = true;
      try {
        for (const watch of watches) {
          if (cancelled) break;
          try {
            const chat = await fetchAssistantChat(watch.chatId);
            const turn = chat.active_turn;
            const stillBusy =
              Boolean(turn?.busy) ||
              turn?.status === "running" ||
              turn?.status === "resuming" ||
              turn?.status === "awaiting_async";
            if (stillBusy) {
              continue;
            }

            const messages = chat.messages || [];
            const assistant = [...messages]
              .reverse()
              .find((message) => message.role === "assistant");
            const isFresh =
              Boolean(assistant) &&
              Number(assistant?.id || 0) > Number(watch.baselineAssistantMessageId || 0);
            const previewSource =
              (isFresh ? assistant?.content : "") ||
              String(turn?.assistant_text || "") ||
              (assistant?.content || "");
            const preview = previewOperatorReply(previewSource);
            unwatchOperatorChat(watch.chatId);
            if (!preview) continue;
            notify.info({
              title: localize(lang, "Оператор ответил", "Operator replied"),
              description: preview,
              duration: 8000,
              action: {
                label: localize(lang, "Открыть", "Open"),
                onClick: () => navigate("/chat"),
              },
            });
          } catch {
            // Keep watching; transient API errors should not drop the watch.
          }
        }
      } finally {
        inFlightRef.current = false;
      }
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [lang, navigate, onChatRoute]);

  return null;
}
