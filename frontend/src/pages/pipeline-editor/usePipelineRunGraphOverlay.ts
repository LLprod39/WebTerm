import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getStudioPipelineRunWsUrl,
  studioRuns,
  type PipelineLastRun,
  type PipelineRun,
} from "@/lib/api";
import { isLivePipelineRunStatus } from "./pipelineGraphUtils";

export function usePipelineRunGraphOverlay({
  graphRunId,
  hasLocalChanges,
  lastRunId,
  pipelineLastRun,
  setGraphRunId,
  setLastRun,
}: {
  graphRunId: number | null;
  hasLocalChanges: boolean;
  lastRunId: number | null | undefined;
  pipelineLastRun: PipelineLastRun | null | undefined;
  setGraphRunId: Dispatch<SetStateAction<number | null>>;
  setLastRun: Dispatch<SetStateAction<PipelineRun | null>>;
}) {
  const [graphRunLive, setGraphRunLive] = useState<PipelineRun | null>(null);
  const { data: graphRunData } = useQuery({
    queryKey: ["studio", "run", graphRunId],
    queryFn: () => (graphRunId ? studioRuns.get(graphRunId) : null),
    enabled: !!graphRunId,
    refetchInterval: (query) => {
      const status = query.state.data?.status || graphRunLive?.status;
      return isLivePipelineRunStatus(status) ? 2000 : false;
    },
    refetchIntervalInBackground: true,
  });

  const clearGraphOverlay = useCallback(() => {
    setGraphRunId(null);
    setGraphRunLive(null);
  }, [setGraphRunId]);

  useEffect(() => {
    setGraphRunLive((current) => (current && current.id === graphRunId ? current : null));
  }, [graphRunId]);

  useEffect(() => {
    if (!graphRunId) {
      setGraphRunLive(null);
      return;
    }
    if (graphRunData) {
      setGraphRunLive(graphRunData);
      if (lastRunId === graphRunData.id) {
        setLastRun(graphRunData);
      }
    }
  }, [graphRunData, graphRunId, lastRunId, setLastRun]);

  useEffect(() => {
    if (hasLocalChanges || graphRunId) {
      return;
    }
    if (!pipelineLastRun?.id || !isLivePipelineRunStatus(pipelineLastRun.status)) {
      return;
    }
    setGraphRunId(pipelineLastRun.id);
  }, [graphRunId, hasLocalChanges, pipelineLastRun?.id, pipelineLastRun?.status, setGraphRunId]);

  useEffect(() => {
    if (!graphRunId || !isLivePipelineRunStatus(graphRunLive?.status || graphRunData?.status)) {
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;
    let attempts = 0;
    let ws: WebSocket | null = null;

    const connect = () => {
      if (cancelled) {
        return;
      }
      ws = new WebSocket(getStudioPipelineRunWsUrl(graphRunId));

      ws.onopen = () => {
        attempts = 0;
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "node_state" && msg.node_id && msg.state) {
            setGraphRunLive((current) => {
              if (!current || current.id !== graphRunId) {
                return current;
              }
              return {
                ...current,
                node_states: {
                  ...(current.node_states || {}),
                  [msg.node_id]: msg.state,
                },
              };
            });
            return;
          }
          if (msg.type === "run_status" && msg.status) {
            setGraphRunLive((current) => {
              if (!current || current.id !== graphRunId) {
                return current;
              }
              return {
                ...current,
                status: typeof msg.status === "string" ? msg.status : current.status,
                error: typeof msg.error === "string" ? msg.error : current.error,
                summary: typeof msg.summary === "string" ? msg.summary : current.summary,
                finished_at: typeof msg.finished_at === "string" ? msg.finished_at : current.finished_at,
                started_at: typeof msg.started_at === "string" ? msg.started_at : current.started_at,
              };
            });
          }
        } catch {
          // ignore malformed live messages
        }
      };

      ws.onclose = () => {
        if (cancelled || !isLivePipelineRunStatus(graphRunLive?.status || graphRunData?.status)) {
          return;
        }
        attempts += 1;
        const delay = Math.min(5000, attempts <= 1 ? 1000 : attempts <= 2 ? 2000 : 4000);
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
    };
  }, [graphRunData?.status, graphRunId, graphRunLive?.status]);

  return {
    clearGraphOverlay,
    graphRunLive,
    setGraphRunLive,
  };
}
