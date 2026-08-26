import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from "react";

import type { AssistantAction, OperatorWsEvent, ProviderBinding } from "@/api";
import { getOperatorChatWsUrl } from "@/lib/api";

import type { ThinkingPhase } from "./OperatorThinkingPanel";

const STREAM_FLUSH_INTERVAL_MS = 36;
const TERMINAL_ERROR_RELEASE_MS = 36;

export type StreamToolStep = {
  id: string;
  name: string;
  status: "running" | "done" | "error";
  preview?: string;
  startedAt?: number;
  completedAt?: number;
};

function mergeSnapshotText(current: string, snapshot: string) {
  if (!snapshot) return current;
  if (!current) return snapshot;
  if (snapshot.startsWith(current)) return snapshot;
  if (current.startsWith(snapshot)) return current;
  return snapshot.length >= current.length ? snapshot : current;
}

function upsertToolStep(steps: StreamToolStep[], step: StreamToolStep) {
  const index = steps.findIndex((item) => item.id === step.id);
  if (index === -1) return [...steps, step];

  const next = [...steps];
  next[index] = {
    ...steps[index],
    ...step,
    startedAt: steps[index].startedAt ?? step.startedAt,
  };
  return next;
}

function toolStepId(data: Record<string, unknown>) {
  return String(data.id || data.call_id || data.name || Math.random());
}

function sanitizeErrorMessage(message: unknown) {
  const normalized = String(message || "Operator chat error")
    .replace(/[\p{Cc}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(
      /((?:password|passwd|token|secret|api[-_ ]?key)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi,
      "$1•••",
    );
  return (normalized || "Operator chat error").slice(0, 800);
}

type LivePlan = {
  title?: string;
  status?: string;
  steps?: Array<{ id?: number; text?: string; status?: string }>;
};

type OperatorHealth = {
  ok: boolean;
  checks?: Record<string, string>;
  issues?: string[];
};

type OperatorAsyncTask = {
  kind: string;
  runId?: number | string;
  status: "running" | "done" | "failed";
};

type OperatorChatWsState = {
  ready: boolean;
  busy: boolean;
  streamText: string;
  toolSteps: StreamToolStep[];
  livePlan: LivePlan | null;
  lastUsage: Record<string, number> | null;
  phase: ThinkingPhase;
  thinkingStartedAt: number | null;
  thinkingIteration: number | null;
  reasoningText: string;
  hasReasoningStream: boolean;
  statusMessage: string;
  health: OperatorHealth | null;
  asyncTask: OperatorAsyncTask | null;
  errorMessage: string | null;
  terminalStatus: string | null;
};

const INITIAL_STATE: OperatorChatWsState = {
  ready: false,
  busy: false,
  streamText: "",
  toolSteps: [],
  livePlan: null,
  lastUsage: null,
  phase: "idle",
  thinkingStartedAt: null,
  thinkingIteration: null,
  reasoningText: "",
  hasReasoningStream: false,
  statusMessage: "",
  health: null,
  asyncTask: null,
  errorMessage: null,
  terminalStatus: null,
};

type OperatorChatWsAction =
  | { type: "chat_reset" }
  | { type: "socket_ready"; health?: OperatorHealth; busy?: boolean; now: number }
  | { type: "socket_closed" }
  | { type: "begin_thinking"; iteration?: number; phase?: ThinkingPhase; now: number }
  | { type: "thinking"; iteration?: number; message?: string; reasoningActive?: boolean; now: number }
  | { type: "thinking_delta"; iteration?: number; now: number }
  | { type: "token_activity" }
  | { type: "stream_flushed"; text: string }
  | { type: "tool_started"; step: StreamToolStep; now: number }
  | { type: "tool_result"; step: StreamToolStep; now: number }
  | { type: "plan_updated"; plan: LivePlan }
  | { type: "usage_updated"; usage: Record<string, number> }
  | { type: "async_started"; task: OperatorAsyncTask; step: StreamToolStep; message: string; now: number }
  | { type: "async_done"; task: OperatorAsyncTask; step: StreamToolStep; message: string; now: number }
  | { type: "awaiting_async" }
  | { type: "turn_parked" }
  | { type: "turn_ended"; status?: string | null }
  | { type: "terminal_error"; message: string }
  | { type: "live_signals_cleared" }
  | { type: "stream_reset" }
  | { type: "message_sent"; now: number }
  | { type: "action_resumed"; message: string; now: number };

function beginThinkingState(
  state: OperatorChatWsState,
  action: { iteration?: number; phase?: ThinkingPhase; now: number },
): OperatorChatWsState {
  const phase =
    action.phase ??
    (state.phase === "streaming" || state.phase === "tools" ? state.phase : "thinking");
  return {
    ...state,
    busy: true,
    phase,
    thinkingStartedAt: state.thinkingStartedAt ?? action.now,
    thinkingIteration: action.iteration ?? state.thinkingIteration,
    errorMessage: null,
    terminalStatus: null,
  };
}

function operatorChatWsReducer(
  state: OperatorChatWsState,
  action: OperatorChatWsAction,
): OperatorChatWsState {
  switch (action.type) {
    case "chat_reset":
      return INITIAL_STATE;
    case "socket_ready": {
      const next = {
        ...state,
        ready: true,
        health: action.health ?? state.health,
      };
      return action.busy ? beginThinkingState(next, action) : next;
    }
    case "socket_closed":
      return state.ready ? { ...state, ready: false } : state;
    case "begin_thinking":
      return beginThinkingState(state, action);
    case "thinking":
      return {
        ...state,
        busy: true,
        phase: "thinking",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        thinkingIteration: action.iteration ?? state.thinkingIteration,
        statusMessage: action.message || state.statusMessage,
        hasReasoningStream: action.reasoningActive || state.hasReasoningStream,
      };
    case "thinking_delta":
      if (
        state.busy &&
        (state.phase === "thinking" || state.phase === "streaming" || state.phase === "tools") &&
        state.thinkingStartedAt != null &&
        state.hasReasoningStream &&
        state.reasoningText === "" &&
        (action.iteration == null || action.iteration === state.thinkingIteration)
      ) {
        return state;
      }
      return {
        ...beginThinkingState(state, action),
        reasoningText: "",
        hasReasoningStream: true,
      };
    case "token_activity":
      if (state.busy && state.phase === "streaming") return state;
      return { ...state, busy: true, phase: "streaming" };
    case "stream_flushed":
      return state.streamText === action.text ? state : { ...state, streamText: action.text };
    case "tool_started":
      return {
        ...state,
        busy: true,
        phase: "tools",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        toolSteps: upsertToolStep(state.toolSteps, action.step),
      };
    case "tool_result":
      return {
        ...state,
        busy: true,
        phase: "thinking",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        toolSteps: upsertToolStep(state.toolSteps, action.step),
      };
    case "plan_updated":
      return { ...state, livePlan: action.plan };
    case "usage_updated":
      return { ...state, lastUsage: action.usage };
    case "async_started":
      return {
        ...state,
        busy: true,
        phase: "tools",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        asyncTask: action.task,
        statusMessage: action.message,
        toolSteps: upsertToolStep(state.toolSteps, action.step),
      };
    case "async_done":
      return {
        ...state,
        busy: true,
        phase: "thinking",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        asyncTask: action.task,
        statusMessage: action.message,
        toolSteps: upsertToolStep(state.toolSteps, action.step),
      };
    case "awaiting_async":
      return {
        ...state,
        busy: true,
        phase: "tools",
        statusMessage: state.statusMessage || "Жду завершения агента…",
      };
    case "turn_parked":
      return { ...state, busy: false, phase: "idle", asyncTask: null };
    case "turn_ended":
      return {
        ...state,
        busy: false,
        phase: "idle",
        thinkingStartedAt: null,
        thinkingIteration: null,
        asyncTask: null,
        terminalStatus: action.status || state.terminalStatus,
      };
    case "terminal_error":
      return {
        ...state,
        busy: false,
        phase: "idle",
        thinkingStartedAt: null,
        thinkingIteration: null,
        asyncTask: null,
        errorMessage: action.message,
        terminalStatus: "error",
      };
    case "live_signals_cleared":
      return {
        ...state,
        streamText: "",
        toolSteps: [],
        livePlan: null,
        reasoningText: "",
        hasReasoningStream: false,
        statusMessage: "",
        thinkingIteration: null,
        asyncTask: null,
      };
    case "stream_reset":
      return {
        ...state,
        streamText: "",
        toolSteps: [],
        livePlan: null,
        reasoningText: "",
        hasReasoningStream: false,
        statusMessage: "",
        thinkingIteration: null,
        errorMessage: null,
        terminalStatus: null,
      };
    case "message_sent":
      return {
        ...state,
        busy: true,
        phase: "thinking",
        thinkingStartedAt: action.now,
        thinkingIteration: 1,
        asyncTask: null,
        errorMessage: null,
        terminalStatus: null,
      };
    case "action_resumed":
      return {
        ...state,
        busy: true,
        phase: "thinking",
        thinkingStartedAt: state.thinkingStartedAt ?? action.now,
        statusMessage: action.message,
        errorMessage: null,
        terminalStatus: null,
      };
  }
}

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
  const [state, dispatch] = useReducer(operatorChatWsReducer, INITIAL_STATE);
  const {
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
    hasReasoningStream,
    statusMessage,
    health,
    asyncTask,
    errorMessage,
    terminalStatus,
  } = state;
  const streamTextRef = useRef("");
  const bufferedTokensRef = useRef("");
  const reasoningSignalRef = useRef<{ active: boolean; iteration: number | null }>({
    active: false,
    iteration: null,
  });
  const streamFlushTimerRef = useRef<number | null>(null);
  const terminalErrorTimerRef = useRef<number | null>(null);
  const stateChatIdRef = useRef(chatId);

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

  const clearStreamFlushTimer = useCallback(() => {
    if (streamFlushTimerRef.current == null) return;
    window.clearTimeout(streamFlushTimerRef.current);
    streamFlushTimerRef.current = null;
  }, []);

  const clearTerminalErrorTimer = useCallback(() => {
    if (terminalErrorTimerRef.current == null) return;
    window.clearTimeout(terminalErrorTimerRef.current);
    terminalErrorTimerRef.current = null;
  }, []);

  const clearLiveTurnSignals = useCallback(() => {
    clearStreamFlushTimer();
    streamTextRef.current = "";
    bufferedTokensRef.current = "";
    reasoningSignalRef.current = { active: false, iteration: null };
    dispatch({ type: "live_signals_cleared" });
  }, [clearStreamFlushTimer]);

  const clearChatState = useCallback(() => {
    clearTerminalErrorTimer();
    clearLiveTurnSignals();
    wsRef.current = null;
    dispatch({ type: "chat_reset" });
  }, [clearLiveTurnSignals, clearTerminalErrorTimer]);

  const scheduleTerminalErrorRelease = useCallback(() => {
    clearTerminalErrorTimer();
    terminalErrorTimerRef.current = window.setTimeout(() => {
      terminalErrorTimerRef.current = null;
      clearLiveTurnSignals();
    }, TERMINAL_ERROR_RELEASE_MS);
  }, [clearLiveTurnSignals, clearTerminalErrorTimer]);

  const flushBufferedTokens = useCallback(() => {
    clearStreamFlushTimer();
    if (!bufferedTokensRef.current) return;
    bufferedTokensRef.current = "";
    dispatch({ type: "stream_flushed", text: streamTextRef.current });
  }, [clearStreamFlushTimer]);

  const scheduleStreamFlush = useCallback(() => {
    if (streamFlushTimerRef.current != null) return;
    streamFlushTimerRef.current = window.setTimeout(() => {
      streamFlushTimerRef.current = null;
      if (!bufferedTokensRef.current) return;
      bufferedTokensRef.current = "";
      dispatch({ type: "stream_flushed", text: streamTextRef.current });
    }, STREAM_FLUSH_INTERVAL_MS);
  }, []);

  const setStreamFromSnapshot = useCallback(
    (snapshot: string) => {
      flushBufferedTokens();
      const next = mergeSnapshotText(streamTextRef.current, snapshot);
      streamTextRef.current = next;
      dispatch({ type: "stream_flushed", text: next });
    },
    [flushBufferedTokens],
  );

  const beginThinking = useCallback((iteration?: number) => {
    dispatch({ type: "begin_thinking", iteration, now: Date.now() });
  }, []);

  const finishTurn = useCallback((terminalStatus?: string | null) => {
    flushBufferedTokens();
    dispatch({ type: "turn_ended", status: terminalStatus });
  }, [flushBufferedTokens]);

  const endTurn = useCallback(() => finishTurn(), [finishTurn]);

  const parkTurn = useCallback(() => {
    flushBufferedTokens();
    dispatch({ type: "turn_parked" });
  }, [flushBufferedTokens]);

  useLayoutEffect(() => {
    if (stateChatIdRef.current === chatId) return;
    stateChatIdRef.current = chatId;
    clearChatState();
  }, [chatId, clearChatState]);

  useEffect(
    () => () => {
      clearStreamFlushTimer();
      clearTerminalErrorTimer();
    },
    [clearStreamFlushTimer, clearTerminalErrorTimer],
  );

  useEffect(() => {
    if (!enabled || !chatId) {
      dispatch({ type: "socket_closed" });
      return;
    }

    let closed = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(getOperatorChatWsUrl(chatId));
      ws = socket;
      wsRef.current = socket;

      socket.onopen = () => {
        if (closed || wsRef.current !== socket) return;
        attempt = 0;
      };

      socket.onmessage = (event) => {
        if (
          closed ||
          stateChatIdRef.current !== chatId ||
          wsRef.current !== socket
        ) {
          return;
        }
        let data: OperatorWsEvent;
        try {
          data = JSON.parse(String(event.data)) as OperatorWsEvent;
        } catch {
          return;
        }
        const type = data.type;
        if (type === "ready") {
          const health =
            "health" in data && data.health && typeof data.health === "object"
              ? (data.health as OperatorHealth)
              : undefined;
          const isBusy = "busy" in data && Boolean(data.busy);
          if (isBusy) clearTerminalErrorTimer();
          dispatch({ type: "socket_ready", health, busy: isBusy, now: Date.now() });
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
          setStreamFromSnapshot(assistantText);
          if (isBusy) {
            clearTerminalErrorTimer();
            dispatch({
              type: "begin_thinking",
              iteration: typeof data.iteration === "number" ? data.iteration : undefined,
              phase: assistantText ? "streaming" : "thinking",
              now: Date.now(),
            });
          } else if (status === "awaiting_confirm") {
            parkTurn();
            const pending = data.pending_action as AssistantAction | null | undefined;
            if (pending && typeof pending === "object" && typeof pending.id === "number") {
              callbacks.current.onConfirmRequired?.(pending);
            }
          } else if (
            ["done", "completed", "failed", "limit", "cancelled", "stopped", "error"].includes(
              status,
            )
          ) {
            finishTurn(status);
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
          clearTerminalErrorTimer();
          beginThinking(1);
          return;
        }
        if (type === "token" && "text" in data && data.text) {
          clearTerminalErrorTimer();
          const token = String(data.text);
          streamTextRef.current += token;
          bufferedTokensRef.current += token;
          scheduleStreamFlush();
          dispatch({ type: "token_activity" });
          callbacks.current.onToken?.(token);
          return;
        }
        if (type === "thinking_delta" && "text" in data && data.text) {
          clearTerminalErrorTimer();
          const iteration = typeof data.iteration === "number" ? data.iteration : undefined;
          if (
            !reasoningSignalRef.current.active ||
            (iteration != null && iteration !== reasoningSignalRef.current.iteration)
          ) {
            reasoningSignalRef.current = {
              active: true,
              iteration: iteration ?? reasoningSignalRef.current.iteration,
            };
            dispatch({ type: "thinking_delta", iteration, now: Date.now() });
          }
          return;
        }
        if (type === "thinking") {
          clearTerminalErrorTimer();
          const iteration = typeof data.iteration === "number" ? data.iteration : undefined;
          const reasoningActive =
            "reasoning_active" in data && data.reasoning_active === true;
          if (reasoningActive) {
            reasoningSignalRef.current = {
              active: true,
              iteration: iteration ?? reasoningSignalRef.current.iteration,
            };
          }
          dispatch({
            type: "thinking",
            iteration,
            message:
              typeof data.message === "string" && data.message ? String(data.message) : undefined,
            reasoningActive,
            now: Date.now(),
          });
          return;
        }
        if (type === "tool_started") {
          clearTerminalErrorTimer();
          const payload = data as Record<string, unknown>;
          const step: StreamToolStep = {
            id: toolStepId(payload),
            name: String(data.name || "tool"),
            status: "running",
            startedAt: Date.now(),
          };
          dispatch({ type: "tool_started", step, now: Date.now() });
          callbacks.current.onToolStep?.(step);
          return;
        }
        if (type === "tool_result") {
          clearTerminalErrorTimer();
          const payload = data as Record<string, unknown>;
          const completedAt = Date.now();
          const step: StreamToolStep = {
            id: toolStepId(payload),
            name: String(data.name || "tool"),
            status: data.ok === false ? "error" : "done",
            preview: data.preview ? String(data.preview) : undefined,
            startedAt: completedAt,
            completedAt,
          };
          dispatch({ type: "tool_result", step, now: completedAt });
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
            dispatch({ type: "plan_updated", plan: data.plan as LivePlan });
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
          parkTurn();
          return;
        }
        if (type === "async_started") {
          clearTerminalErrorTimer();
          // Agent/playbook launched — stay "busy" in a waiting phase until async_done.
          const runId = "run_id" in data ? data.run_id : undefined;
          const kind = "async_kind" in data ? data.async_kind : "agent_run";
          const task: OperatorAsyncTask = {
            kind: String(kind || "agent_run"),
            runId: runId as number | string | undefined,
            status: "running",
          };
          const message =
            runId
              ? `Жду ${String(kind)} #${runId}…`
              : `Жду завершения ${String(kind)}…`;
          const now = Date.now();
          const step: StreamToolStep = {
            id: `async-${runId || kind}`,
            name: String(kind || "async_run"),
            status: "running",
            preview: runId ? `run #${runId}` : undefined,
            startedAt: now,
          };
          dispatch({ type: "async_started", task, step, message, now });
          return;
        }
        if (type === "async_done") {
          clearTerminalErrorTimer();
          const runId = "run_id" in data ? data.run_id : undefined;
          const kind = "async_kind" in data ? data.async_kind : "async_run";
          const ok = "ok" in data ? Boolean(data.ok) : true;
          const task: OperatorAsyncTask = {
            kind: String(kind || "async_run"),
            runId: runId as number | string | undefined,
            status: ok ? "done" : "failed",
          };
          const id = `async-${runId || kind}`;
          const completedAt = Date.now();
          const step: StreamToolStep = {
            id,
            name: String(kind || "async_run"),
            status: ok ? "done" : "error",
            preview: `${data.status || (ok ? "done" : "failed")}${runId ? ` #${runId}` : ""}`,
            startedAt: completedAt,
            completedAt,
          };
          const message =
            ok
              ? `Агент/задача завершены${runId ? ` (#${runId})` : ""} — пишу итог…`
              : `Агент/задача завершились с ошибкой${runId ? ` (#${runId})` : ""} — разбираю…`;
          dispatch({ type: "async_done", task, step, message, now: completedAt });
          return;
        }
        if (type === "action_update" && data.action) {
          callbacks.current.onActionUpdate?.(data.action as AssistantAction);
          return;
        }
        if (type === "usage" && data.usage) {
          dispatch({ type: "usage_updated", usage: data.usage as Record<string, number> });
          return;
        }
        if (type === "turn_done" || type === "turn_complete") {
          flushBufferedTokens();
          const status = String(data.status || "");
          // Parked turns (confirm / async wait) are not "idle" for the operator —
          // keep a quiet waiting state so the UI doesn't look abandoned.
          if (status === "awaiting_async") {
            dispatch({ type: "awaiting_async" });
          } else if (status === "awaiting_confirm") {
            parkTurn();
          } else {
            finishTurn(status || "completed");
          }
          callbacks.current.onTurnComplete?.({
            status: data.status as string | undefined,
            actions: data.actions as AssistantAction[] | undefined,
          });
          return;
        }
        if (type === "error") {
          flushBufferedTokens();
          const message = sanitizeErrorMessage(data.message);
          dispatch({ type: "terminal_error", message });
          callbacks.current.onError?.(message);
          scheduleTerminalErrorRelease();
        }
      };

      socket.onclose = () => {
        const ownsCurrentSocket = wsRef.current === socket;
        if (ownsCurrentSocket) wsRef.current = null;
        // Keep busy/stream — turn may continue in background on the server.
        if (closed || !ownsCurrentSocket || stateChatIdRef.current !== chatId) return;
        dispatch({ type: "socket_closed" });
        attempt += 1;
        const delay = Math.min(8_000, 500 * 2 ** Math.min(attempt, 4));
        retryTimer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      const ownedSocket = ws;
      if (ownedSocket && ownedSocket.readyState !== WebSocket.CLOSED) ownedSocket.close();
      if (wsRef.current === ownedSocket) {
        wsRef.current = null;
        dispatch({ type: "socket_closed" });
      }
    };
  }, [
    chatId,
    enabled,
    beginThinking,
    clearTerminalErrorTimer,
    finishTurn,
    flushBufferedTokens,
    parkTurn,
    scheduleStreamFlush,
    scheduleTerminalErrorRelease,
    setStreamFromSnapshot,
  ]);

  const resetStream = useCallback(() => {
    clearTerminalErrorTimer();
    clearStreamFlushTimer();
    streamTextRef.current = "";
    bufferedTokensRef.current = "";
    reasoningSignalRef.current = { active: false, iteration: null };
    dispatch({ type: "stream_reset" });
  }, [clearStreamFlushTimer, clearTerminalErrorTimer]);

  const hydrateFromSnapshot = useCallback(
    (text: string, opts?: { busy?: boolean; iteration?: number }) => {
      if (opts?.busy) clearTerminalErrorTimer();
      setStreamFromSnapshot(text);
      if (opts?.busy) {
        dispatch({
          type: "begin_thinking",
          iteration: opts.iteration,
          phase: text ? "streaming" : "thinking",
          now: Date.now(),
        });
      }
    },
    [clearTerminalErrorTimer, setStreamFromSnapshot],
  );

  const sendMessage = useCallback(
    (message: string, providerBinding?: ProviderBinding | null) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return false;
      }
      resetStream();
      dispatch({ type: "message_sent", now: Date.now() });
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
    clearTerminalErrorTimer();
    // Do not wipe streamText / existing UI — confirm resumes the same turn.
    dispatch({ type: "action_resumed", message: "Подтверждено — выполняю…", now: Date.now() });
    ws.send(
      JSON.stringify({
        type: "action.confirm",
        action_id: actionId,
        typed_confirm: typedConfirm || "",
      }),
    );
    return true;
  }, [clearTerminalErrorTimer]);

  const cancelAction = useCallback((actionId: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    clearTerminalErrorTimer();
    dispatch({ type: "action_resumed", message: "Отмена…", now: Date.now() });
    ws.send(
      JSON.stringify({
        type: "action.cancel",
        action_id: actionId,
      }),
    );
    return true;
  }, [clearTerminalErrorTimer]);

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
    errorMessage,
    terminalStatus,
    sendMessage,
    stopTurn,
    confirmAction,
    cancelAction,
    resetStream,
    hydrateFromSnapshot,
    endTurn,
  };
}
