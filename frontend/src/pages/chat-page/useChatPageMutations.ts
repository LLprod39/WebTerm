import type { Dispatch, SetStateAction } from "react";
import { useMutation, type QueryClient } from "@tanstack/react-query";

import {
  cancelAssistantAction,
  confirmAssistantAction,
  createAssistantChat,
  deleteAssistantChat,
  sendAssistantChatMessage,
  startAssistantChat,
  updateAssistantChat,
  type AssistantChatSession,
} from "@/api";
import type { useToast } from "@/hooks/use-toast";
import { localize } from "@/lib/i18n";

import type { PinnedServer, PinnedUser } from "./ComposeCommandPalette";
import type { PinnedPlaybook } from "./useChatPagePins";
import { mergeTurnIntoChat, replaceActionInChat } from "./chatHelpers";
import { LAST_CHAT_KEY } from "./chatPageSession";

type ToastFn = ReturnType<typeof useToast>["toast"];
type Lang = "ru" | "en" | string;
type SetSearchParams = (
  nextInit: Record<string, string> | URLSearchParams,
  navigateOpts?: { replace?: boolean },
) => void;

export type UseChatPageMutationsParams = {
  activeChatId: number | null;
  lang: Lang;
  toast: ToastFn;
  queryClient: QueryClient;
  setSearchParams: SetSearchParams;
  setDraft: Dispatch<SetStateAction<string>>;
  pendingUserText: string | null;
  setPendingUserText: Dispatch<SetStateAction<string | null>>;
  setPendingSend: Dispatch<SetStateAction<string | null>>;
  promoteNewPendingChat: (chatId: number) => void;
  setActionWorkingId: Dispatch<SetStateAction<number | null>>;
  setRenamingChatId: Dispatch<SetStateAction<number | null>>;
  pinnedServers: PinnedServer[];
  pinnedUsers: PinnedUser[];
  pinnedPlaybook: PinnedPlaybook | null;
};

export function useChatPageMutations({
  activeChatId,
  lang,
  toast,
  queryClient,
  setSearchParams,
  setDraft,
  pendingUserText,
  setPendingUserText,
  setPendingSend,
  promoteNewPendingChat,
  setActionWorkingId,
  setRenamingChatId,
  pinnedServers,
  pinnedUsers,
  pinnedPlaybook,
}: UseChatPageMutationsParams) {
  const sendMutation = useMutation({
    mutationFn: (message: string) => (
      activeChatId ? sendAssistantChatMessage(activeChatId, message) : startAssistantChat(message)
    ),
    onSuccess: (turn) => {
      queryClient.setQueryData<AssistantChatSession>(
        ["assistant", "chat", turn.chat.id],
        (previous) => mergeTurnIntoChat(previous, turn),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(turn.chat.id) });
      setDraft("");
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Чат не ответил", "Chat failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const createChatMutation = useMutation({
    mutationFn: () => createAssistantChat(),
    onSuccess: (chat) => {
      promoteNewPendingChat(chat.id);
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(chat.id) });
      // Persist pins chosen before the chat existed
      if (pinnedServers.length || pinnedUsers.length || pinnedPlaybook) {
        void updateAssistantChat(chat.id, {
          pinned_context: {
            servers: pinnedServers.map((s) => ({ id: s.id, name: s.name, host: s.host || "" })),
            users: pinnedUsers.map((u) => ({ id: u.id, username: u.username })),
            playbook: pinnedPlaybook
              ? { id: pinnedPlaybook.id, name: pinnedPlaybook.name, kind: pinnedPlaybook.kind || "" }
              : null,
          },
        }).then((updated) => {
          queryClient.setQueryData<AssistantChatSession>(
            ["assistant", "chat", chat.id],
            (previous) => ({
              ...(previous ?? chat),
              ...updated,
              // The pin request can finish after WebSocket/REST has already
              // populated the new chat. Never replace that fresher turn with
              // the empty snapshot returned by createAssistantChat().
              messages: previous?.messages ?? chat.messages ?? [],
              active_turn: previous?.active_turn ?? chat.active_turn,
            }),
          );
        }).catch(() => {
          // Best effort: the locally selected pins are still included in the
          // first message context and must not break the chat if saving fails.
        });
      }
    },
    onError: (error) => {
      if (pendingUserText) setDraft((current) => current || pendingUserText);
      setPendingSend(null);
      setPendingUserText(null);
      toast({
        title: localize(lang, "Чат не создан", "Chat was not created"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({
      actionId,
      intent,
      typedConfirm,
    }: {
      actionId: number;
      intent: "confirm" | "cancel";
      typedConfirm?: string;
    }) => (
      intent === "confirm"
        ? confirmAssistantAction(actionId, typedConfirm)
        : cancelAssistantAction(actionId)
    ),
    onMutate: ({ actionId }) => {
      setActionWorkingId(actionId);
    },
    onSuccess: (action) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", action.chat_id] });
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Действие не выполнено", "Action failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
    onSettled: () => {
      setActionWorkingId(null);
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ chatId, title }: { chatId: number; title: string }) =>
      updateAssistantChat(chatId, { title }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      if (activeChatId) {
        void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", activeChatId] });
      }
      setRenamingChatId(null);
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Не удалось переименовать", "Rename failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const deleteChatMutation = useMutation({
    mutationFn: (chatId: number) => deleteAssistantChat(chatId),
    onSuccess: (_res, chatId) => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      queryClient.removeQueries({ queryKey: ["assistant", "chat", chatId] });
      if (chatId === activeChatId) {
        try {
          localStorage.removeItem(LAST_CHAT_KEY);
        } catch {
          // ignore
        }
        setSearchParams({});
      }
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Не удалось удалить чат", "Delete failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  return {
    sendMutation,
    createChatMutation,
    actionMutation,
    renameMutation,
    deleteChatMutation,
  };
}
