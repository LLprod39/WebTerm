import { useCallback, useEffect, useRef, useState } from "react";

import type { AssistantAction, OperatorWsEvent, ProviderBinding } from "@/api";
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
  onSshSession?: (payload: Record<string, unknown>) => void;
  onToolResultDetail?: (payload: Record<string, unknown>) => void;
  onConfirmRequired?: (action: AssistantAction | { id: number }) => void;
  onActionUpdate?: (action: AssistantAction) => void;
  onTurnComplete?: (payload: { status?: string; actions?: AssistantAction[] }) => void;
  onError?: (message: string) => void;
  onSnapshot?: (payload: {
    status?: string;
    busy?: boolean;
    assistantText?: string;
    userText?: string;
    action?: AssistantAction | null;
  }) => void;
};

export function useOperatorChatWs({
  chatId,
  enabled = true,
  onToken,
  onToolStep,
  onSshSession,
  onToolResultDetail,
  onConfirmRequired,
  onActionUpdate,
  onTurnComplete,
  onError,
  onSnapshot,
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
  /** True after first real thinking_delta (not just status heartbeats). */
  const [hasReasoningStream, setHasReasoningStream] = useState(false);
  /** Last status message from backend (e.g. "Генерация JSON…"). */
  const [statusMessage, setStatusMessage] = useState("");
  /** Backend readiness probe (channel layer + LLM). Null until first "ready". */
  const [health, setHealth] = useState<{
    ok: boolean;
    checks?: Record<string, string>;
    issues?: string[];
  } | null>(null);
  /** A long-running spawned task (agent / pipeline run) the operator is waiting on. */
  const [asyncTask, setAsyncTask] = useState<{
    kind: string;
    runId?: number | string;
    status: "running" | "done" | "failed";
  } | null>(null);

  const callbacks = useRef({
    onToken,
    onToolStep,
    onSshSession,
    onToolResultDetail,
    onConfirmRequired,
    onActionUpdate,
    onTurnComplete,
    onError,
    onSnapshot,
  });
  callbacks.current = {
    onToken,
    onToolStep,
    onSshSession,
    onToolResultDetail,
    onConfirmRequired,
    onActionUpdate,
    onTurnComplete,
    onError,
    onSnapshot,
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
    setAsyncTask(null);
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
          if ("health" in data && data.health && typeof data.health === "object") {
            setHealth(
              data.health as { ok: boolean; checks?: Record<string, string>; issues?: string[] },
            );
          }
          if ("busy" in data && data.busy) {
            beginThinking();
          }
          return;
        }
        if (type === "turn_snapshot") {
          const assistantText = String(data.assistant_text || "");
          const userText = String(data.user_text || "");
          const status = String(data.status || "");
          const isBusy =
            Boolean(data.busy || data.in_process) ||
            status === "running" ||
            status === "resuming" ||
            status === "awaiting_async";
          if (assistantText) {
            setStreamText(assistantText);
          }
          if (isBusy) {
            beginThinking(typeof data.iteration === "number" ? data.iteration : undefined);
            setPhase(assistantText ? "streaming" : "thinking");
          } else if (status === "awaiting_confirm") {
            endTurn();
            const pending = data.pending_action as AssistantAction | null | undefined;
            if (pending && typeof pending === "object" && typeof pending.id === "number") {
              callbacks.current.onConfirmRequired?.(pending);
            }
          }
          callbacks.current.onSnapshot?.({
            status,
            busy: isBusy,
            assistantText,
            userText,
            action: (data.pending_action as AssistantAction | null | undefined) || null,
          });
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
          setHasReasoningStream(true);
          setReasoningText((prev) => (prev + String(data.text)).slice(-8000));
          beginThinking(typeof data.iteration === "number" ? data.iteration : undefined);
          return;
        }
        if (type === "thinking") {
          const iter = typeof data.iteration === "number" ? data.iteration : undefined;
          setPhase("thinking");
          setBusy(true);
          setThinkingStartedAt((prev) => prev ?? Date.now());
          if (iter != null) setThinkingIteration(iter);
          if (typeof data.message === "string" && data.message) {
            setStatusMessage(String(data.message));
          }
          if ("reasoning_active" in data && data.reasoning_active === true) {
            setHasReasoningStream(true);
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
          setPhase("thinking");
          setThinkingStartedAt(Date.now());
          callbacks.current.onToolStep?.(step);
          callbacks.current.onToolResultDetail?.(data as Record<string, unknown>);
          if (data.action) {
            callbacks.current.onActionUpdate?.(data.action as AssistantAction);
          }
          return;
        }
        if (type === "ssh_session") {
          callbacks.current.onSshSession?.(data as Record<string, unknown>);
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
        if (type === "async_started") {
          // Agent/playbook launched — stay "busy" in a waiting phase until async_done.
          setBusy(true);
          setPhase("tools");
          setThinkingStartedAt((prev) => prev ?? Date.now());
          const runId = "run_id" in data ? data.run_id : undefined;
          const kind = "async_kind" in data ? data.async_kind : "agent_run";
          setAsyncTask({
            kind: String(kind || "agent_run"),
            runId: runId as number | string | undefined,
            status: "running",
          });
          setStatusMessage(
            runId
              ? `Жду ${String(kind)} #${runId}…`
              : `Жду завершения ${String(kind)}…`,
          );
          setToolSteps((prev) => {
            const id = `async-${runId || kind}`;
            const step: StreamToolStep = {
              id,
              name: String(kind || "async_run"),
              status: "running",
              preview: runId ? `run #${runId}` : undefined,
            };
            return [...prev.filter((s) => s.id !== id), step];
          });
          return;
        }
        if (type === "async_done") {
          const runId = "run_id" in data ? data.run_id : undefined;
          const kind = "async_kind" in data ? data.async_kind : "async_run";
          const ok = "ok" in data ? Boolean(data.ok) : true;
          setAsyncTask({
            kind: String(kind || "async_run"),
            runId: runId as number | string | undefined,
            status: ok ? "done" : "failed",
          });
          const id = `async-${runId || kind}`;
          setToolSteps((prev) => {
            const step: StreamToolStep = {
              id,
              name: String(kind || "async_run"),
              status: ok ? "done" : "error",
              preview: `${data.status || (ok ? "done" : "failed")}${runId ? ` #${runId}` : ""}`,
            };
            return [...prev.filter((s) => s.id !== id), step];
          });
          setStatusMessage(
            ok
              ? `Агент/задача завершены${runId ? ` (#${runId})` : ""} — пишу итог…`
              : `Агент/задача завершились с ошибкой${runId ? ` (#${runId})` : ""} — разбираю…`,
          );
          setBusy(true);
          setPhase("thinking");
          setThinkingStartedAt(Date.now());
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
          const status = String(data.status || "");
          // Parked turns (confirm / async wait) are not "idle" for the operator —
          // keep a quiet waiting state so the UI doesn't look abandoned.
          if (status === "awaiting_async") {
            setBusy(true);
            setPhase("tools");
            setStatusMessage((prev) => prev || "Жду завершения агента…");
          } else if (status === "awaiting_confirm") {
            endTurn();
          } else {
            endTurn();
          }
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
        // Keep busy/stream — turn may continue in background on the server.
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
    setHasReasoningStream(false);
    setStatusMessage("");
    setThinkingIteration(null);
  }, []);

  const hydrateFromSnapshot = useCallback(
    (text: string, opts?: { busy?: boolean; iteration?: number }) => {
      if (text) setStreamText(text);
      if (opts?.busy) {
        beginThinking(opts.iteration);
        setPhase(text ? "streaming" : "thinking");
      }
    },
    [beginThinking],
  );

  const sendMessage = useCallback(
    (message: string, providerBinding?: ProviderBinding | null) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return false;
      }
      resetStream();
      setBusy(true);
      setPhase("thinking");
      setThinkingStartedAt(Date.now());
      setThinkingIteration(1);
      // Reasoning mode is decided server-side by the admin model config
      ws.send(JSON.stringify({
        type: "chat.message",
        message,
        ...(providerBinding ? { provider_binding: providerBinding } : {}),
      }));
      return true;
    },
    [resetStream],
  );

  const stopTurn = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "turn.stop" }));
    return true;
  }, []);

  const confirmAction = useCallback((actionId: number, typedConfirm?: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    // Do not wipe streamText / existing UI — confirm resumes the same turn.
    setBusy(true);
    setPhase("thinking");
    setThinkingStartedAt(Date.now());
    setStatusMessage("Подтверждено — выполняю…");
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
    setStatusMessage("Отмена…");
    ws.send(
      JSON.stringify({
        type: "action.cancel",
        action_id: actionId,
      }),
    );
    return true;
  }, []);

  return {
    ready,
    busy,
    health,
    asyncTask,
    streamText,
    toolSteps,
    livePlan,
    lastUsage,
    phase,
    thinkingStartedAt,
    thinkingIteration,
    reasoningText,
    hasReasoningStream,
    statusMessage,
    sendMessage,
    stopTurn,
    confirmAction,
    cancelAction,
    resetStream,
    hydrateFromSnapshot,
    endTurn,
  };
}
