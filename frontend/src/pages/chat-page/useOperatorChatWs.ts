import { useCallback, useEffect, useRef, useState } from "react";

import type { AssistantAction, OperatorWsEvent } from "@/api";
import { getOperatorChatWsUrl } from "@/lib/api";

import type { ThinkingPhase } from "./OperatorThinkingPanel";

export type StreamToolStep = {
  id: string;
  name: string;
  status: "running" | "done" | "error";
  preview?: string;
};

type UseOperatorChatWsOptions = {
  chatId: number | null;
  enabled?: boolean;
  onToken?: (text: string) => void;
  onToolStep?: (step: StreamToolStep) => void;
  onConfirmRequired?: (action: AssistantAction | { id: number }) => void;
  onActionUpdate?: (action: AssistantAction) => void;
  onTurnComplete?: (payload: { status?: string; actions?: AssistantAction[] }) => void;
  onError?: (message: string) => void;
};

export function useOperatorChatWs({
  chatId,
  enabled = true,
  onToken,
  onToolStep,
  onConfirmRequired,
  onActionUpdate,
  onTurnComplete,
  onError,
}: UseOperatorChatWsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [toolSteps, setToolSteps] = useState<StreamToolStep[]>([]);
  const [livePlan, setLivePlan] = useState<{
    title?: string;
    status?: string;
    steps?: Array<{ id?: number; text?: string; status?: string }>;
  } | null>(null);
  const [lastUsage, setLastUsage] = useState<Record<string, number> | null>(null);
  const [phase, setPhase] = useState<ThinkingPhase>("idle");
  const [thinkingStartedAt, setThinkingStartedAt] = useState<number | null>(null);
  const [thinkingIteration, setThinkingIteration] = useState<number | null>(null);
  const [reasoningText, setReasoningText] = useState("");

  const callbacks = useRef({
    onToken,
    onToolStep,
    onConfirmRequired,
    onActionUpdate,
    onTurnComplete,
    onError,
  });
  callbacks.current = {
    onToken,
    onToolStep,
    onConfirmRequired,
    onActionUpdate,
    onTurnComplete,
    onError,
  };

  const beginThinking = useCallback((iteration?: number) => {
    setBusy(true);
    setPhase((prev) => (prev === "streaming" || prev === "tools" ? prev : "thinking"));
    setThinkingStartedAt((prev) => prev ?? Date.now());
    if (typeof iteration === "number") setThinkingIteration(iteration);
  }, []);

  const endTurn = useCallback(() => {
    setBusy(false);
    setPhase("idle");
    setThinkingStartedAt(null);
    setThinkingIteration(null);
  }, []);

  useEffect(() => {
    if (!enabled || !chatId) {
      setReady(false);
      return;
    }

    let closed = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;

    const connect = () => {
      if (closed) return;
      ws = new WebSocket(getOperatorChatWsUrl(chatId));
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
      };

      ws.onmessage = (event) => {
        let data: OperatorWsEvent;
        try {
          data = JSON.parse(String(event.data)) as OperatorWsEvent;
        } catch {
          return;
        }
        const type = data.type;
        if (type === "ready") {
          setReady(true);
          return;
        }
        if (type === "turn_started") {
          beginThinking(1);
          return;
        }
        if (type === "token" && "text" in data && data.text) {
          setStreamText((prev) => prev + String(data.text));
          setPhase("streaming");
          setBusy(true);
          callbacks.current.onToken?.(String(data.text));
          return;
        }
        if (type === "thinking_delta" && "text" in data && data.text) {
          setReasoningText((prev) => (prev + String(data.text)).slice(-6000));
          beginThinking(typeof data.iteration === "number" ? data.iteration : undefined);
          return;
        }
        if (type === "thinking") {
          const iter = typeof data.iteration === "number" ? data.iteration : undefined;
          // New LLM round after tools — back to thinking
          setPhase("thinking");
          setBusy(true);
          setThinkingStartedAt(Date.now());
          if (iter != null) setThinkingIteration(iter);
          if (typeof data.message === "string" && data.message) {
            setReasoningText((prev) => (prev ? `${prev}\n` : "") + data.message);
          }
          return;
        }
        if (type === "tool_started") {
          const step: StreamToolStep = {
            id: String(data.id || data.name || Math.random()),
            name: String(data.name || "tool"),
            status: "running",
          };
          setToolSteps((prev) => [...prev.filter((s) => s.id !== step.id), step]);
          setPhase("tools");
          setBusy(true);
          setThinkingStartedAt((prev) => prev ?? Date.now());
          callbacks.current.onToolStep?.(step);
          return;
        }
        if (type === "tool_result") {
          const step: StreamToolStep = {
            id: String(data.id || data.name || Math.random()),
            name: String(data.name || "tool"),
            status: data.ok === false ? "error" : "done",
            preview: data.preview ? String(data.preview) : undefined,
          };
          setToolSteps((prev) => {
            const rest = prev.filter((s) => s.id !== step.id);
            return [...rest, step];
          });
          // After tools, model thinks again until next tokens
          setPhase("thinking");
          setThinkingStartedAt(Date.now());
          callbacks.current.onToolStep?.(step);
          if (data.action) {
            callbacks.current.onActionUpdate?.(data.action as AssistantAction);
          }
          return;
        }
        if (type === "plan_update") {
          if (data.plan && typeof data.plan === "object") {
            setLivePlan(
              data.plan as {
                title?: string;
                status?: string;
                steps?: Array<{ id?: number; text?: string; status?: string }>;
              },
            );
          }
          return;
        }
        if (type === "artifact") {
          return;
        }
        if (type === "confirm_required") {
          const action = (data.action || { id: data.action_id }) as AssistantAction | { id: number };
          if (action && "id" in action && action.id) {
            callbacks.current.onConfirmRequired?.(action);
          }
          endTurn();
          return;
        }
        if (type === "action_update" && data.action) {
          callbacks.current.onActionUpdate?.(data.action as AssistantAction);
          return;
        }
        if (type === "usage" && data.usage) {
          setLastUsage(data.usage as Record<string, number>);
          return;
        }
        if (type === "turn_done" || type === "turn_complete") {
          endTurn();
          callbacks.current.onTurnComplete?.({
            status: data.status as string | undefined,
            actions: data.actions as AssistantAction[] | undefined,
          });
          return;
        }
        if (type === "error") {
          endTurn();
          callbacks.current.onError?.(String(data.message || "Operator chat error"));
        }
      };

      ws.onclose = () => {
        setReady(false);
        wsRef.current = null;
        if (closed) return;
        attempt += 1;
        const delay = Math.min(8_000, 500 * 2 ** Math.min(attempt, 4));
        retryTimer = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
      wsRef.current = null;
      setReady(false);
    };
  }, [chatId, enabled, beginThinking, endTurn]);

  const resetStream = useCallback(() => {
    setStreamText("");
    setToolSteps([]);
    setLivePlan(null);
    setReasoningText("");
    setThinkingIteration(null);
  }, []);

  const sendMessage = useCallback(
    (message: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return false;
      }
      resetStream();
      setBusy(true);
      setPhase("thinking");
      setThinkingStartedAt(Date.now());
      setThinkingIteration(1);
      ws.send(JSON.stringify({ type: "chat.message", message }));
      return true;
    },
    [resetStream],
  );

  const confirmAction = useCallback((actionId: number, typedConfirm?: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    setBusy(true);
    setPhase("thinking");
    setThinkingStartedAt(Date.now());
    ws.send(
      JSON.stringify({
        type: "action.confirm",
        action_id: actionId,
        typed_confirm: typedConfirm || "",
      }),
    );
    return true;
  }, []);

  const cancelAction = useCallback((actionId: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    setBusy(true);
    setPhase("thinking");
    setThinkingStartedAt(Date.now());
    ws.send(JSON.stringify({ type: "action.cancel", action_id: actionId }));
    return true;
  }, []);

  return {
    ready,
    busy,
    streamText,
    toolSteps,
    livePlan,
    lastUsage,
    phase,
    thinkingStartedAt,
    thinkingIteration,
    reasoningText,
    sendMessage,
    confirmAction,
    cancelAction,
    resetStream,
  };
}
