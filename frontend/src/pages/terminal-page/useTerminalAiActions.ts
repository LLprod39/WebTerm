import { useCallback, type MutableRefObject } from "react";

import {
  AI_PREFERENCES_STORAGE_KEY,
  cloneAiPreferences,
} from "@/components/terminal/ai-preferences";
import type {
  AiCommand,
  AiPreferences,
} from "@/components/terminal/ai-types";
import type { TerminalHandle } from "@/components/terminal/XTerminal";
import { toast } from "@/hooks/use-toast";

import {
  createEmptyAiState,
  nextId,
  type TabAiState,
} from "./model";

type UpdateTabAiState = (tabId: string, updater: (state: TabAiState) => TabAiState) => void;
type UpdateActiveTabAiState = (updater: (state: TabAiState) => TabAiState) => void;
type UpdateTabAiPreferences = (tabId: string, updater: (state: AiPreferences) => AiPreferences) => void;

export function useTerminalAiActions({
  activeTabIdRef,
  terminalRefs,
  tabAiPreferences,
  globalAiPreferences,
  updateTabAiState,
  updateActiveTabAiState,
  updateTabAiPreferences,
  setGlobalAiPreferences,
}: {
  activeTabIdRef: MutableRefObject<string>;
  terminalRefs: MutableRefObject<Record<string, TerminalHandle | null>>;
  tabAiPreferences: Record<string, AiPreferences>;
  globalAiPreferences: AiPreferences;
  updateTabAiState: UpdateTabAiState;
  updateActiveTabAiState: UpdateActiveTabAiState;
  updateTabAiPreferences: UpdateTabAiPreferences;
  setGlobalAiPreferences: (preferences: AiPreferences) => void;
}) {
  const handleSendAi = useCallback((text: string) => {
    if (!text.trim()) return;
    const tabId = activeTabIdRef.current;
    const preferences = tabAiPreferences[tabId] || globalAiPreferences;
    const trimmed = text.trim();

    if (trimmed.toLowerCase().startsWith("/mode")) {
      const [, rawMode = ""] = trimmed.split(/\s+/, 2);
      const normalizedMode = rawMode.trim().toLowerCase();
      const currentMode = preferences.chatMode;

      if (!normalizedMode) {
        updateActiveTabAiState((state) => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: nextId(),
              role: "assistant",
              type: "text",
              content: `Текущий режим: **${currentMode === "agent" ? "Agent" : "Ask"}**.\n\nИспользуйте \`/mode ask\` или \`/mode agent\`.`,
            },
          ],
        }));
        return;
      }

      if (normalizedMode !== "ask" && normalizedMode !== "agent") {
        updateActiveTabAiState((state) => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: nextId(),
              role: "assistant",
              type: "text",
              content: "Неизвестный режим. Доступно: `/mode ask`, `/mode agent`.",
            },
          ],
        }));
        return;
      }

      updateTabAiPreferences(tabId, (state) => ({
        ...state,
        chatMode: normalizedMode,
      }));
      updateActiveTabAiState((state) => ({
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "assistant",
            type: "text",
            content:
              normalizedMode === "agent"
                ? "Режим переключён на **Agent**. AI будет сразу запускать безопасные команды, а опасные действия по-прежнему потребуют подтверждения."
                : "Режим переключён на **Ask**. AI будет объяснять и предлагать команды, а запуск останется только после вашего подтверждения.",
          },
        ],
      }));
      return;
    }

    updateActiveTabAiState((state) => ({
      ...state,
      isGenerating: true,
      messages: [...state.messages, { id: nextId(), role: "user", type: "text", content: text }],
    }));
    terminalRefs.current[tabId]?.sendAiRequest(
      text,
      preferences.chatMode,
      preferences.executionMode,
      preferences.settings,
    );
  }, [
    activeTabIdRef,
    globalAiPreferences,
    tabAiPreferences,
    terminalRefs,
    updateActiveTabAiState,
    updateTabAiPreferences,
  ]);

  const handleStopAi = useCallback(() => {
    updateActiveTabAiState((state) => ({
      ...state,
      isGenerating: false,
    }));
    terminalRefs.current[activeTabIdRef.current]?.stopAi();
  }, [activeTabIdRef, terminalRefs, updateActiveTabAiState]);

  const handleConfirm = useCallback((id: number) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiConfirm(id);
  }, [activeTabIdRef, terminalRefs]);

  const handleCancel = useCallback((id: number) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiCancel(id);
  }, [activeTabIdRef, terminalRefs]);

  const handleReply = useCallback((qId: string, text: string) => {
    updateActiveTabAiState((state) => ({
      ...state,
      messages: state.messages.map((message) =>
        message.qId === qId
          ? {
              ...message,
              questionAnswered: true,
              questionAnswer: text,
            }
          : message,
      ),
    }));
    terminalRefs.current[activeTabIdRef.current]?.sendAiReply(qId, text);
  }, [activeTabIdRef, terminalRefs, updateActiveTabAiState]);

  const handleGenerateReport = useCallback((force = false) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiGenerateReport(force);
  }, [activeTabIdRef, terminalRefs]);

  const handleClearAiMemory = useCallback(() => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiClearMemory();
  }, [activeTabIdRef, terminalRefs]);

  const handleExplainCommand = useCallback((cmd: AiCommand) => {
    const tabId = activeTabIdRef.current;
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: state.messages.map((message) => {
        if (message.type !== "commands" || !message.commands?.some((c) => c.id === cmd.id)) return message;
        return {
          ...message,
          commands: message.commands.map((c) => (c.id === cmd.id ? { ...c, explaining: true } : c)),
        };
      }),
    }));
    terminalRefs.current[tabId]?.sendAiExplainOutput({
      id: cmd.id,
      cmd: cmd.cmd,
      output: cmd.direct_output ?? "",
      exit_code: cmd.exit_code,
    });
  }, [activeTabIdRef, terminalRefs, updateTabAiState]);

  const handleSaveAiDefaults = useCallback((activePreferences: AiPreferences) => {
    const next = cloneAiPreferences(activePreferences);
    setGlobalAiPreferences(next);
    try {
      localStorage.setItem(AI_PREFERENCES_STORAGE_KEY, JSON.stringify(next));
      localStorage.removeItem("ai_execution_mode");
    } catch {
      // noop
    }
    toast({
      title: "Глобальные настройки сохранены",
      description: "Новые чаты будут стартовать с текущими параметрами.",
    });
  }, [setGlobalAiPreferences]);

  const handleResetAiPreferences = useCallback(() => {
    updateTabAiPreferences(activeTabIdRef.current, () => cloneAiPreferences(globalAiPreferences));
    toast({
      title: "Настройки чата сброшены",
      description: "Для текущего чата снова применены глобальные значения по умолчанию.",
    });
  }, [activeTabIdRef, globalAiPreferences, updateTabAiPreferences]);

  const handleClearChat = useCallback(() => {
    updateActiveTabAiState(() => createEmptyAiState());
  }, [updateActiveTabAiState]);

  return {
    handleSendAi,
    handleStopAi,
    handleConfirm,
    handleCancel,
    handleReply,
    handleGenerateReport,
    handleClearAiMemory,
    handleExplainCommand,
    handleSaveAiDefaults,
    handleResetAiPreferences,
    handleClearChat,
  };
}
