import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";

import { getPlaybookRun, type PlaybookRun } from "@/api/playbooks";
import type { PlaybooksView } from "./types";

interface RunPollingArgs {
  view: PlaybooksView;
  queryClient: QueryClient;
  setActiveRun: Dispatch<SetStateAction<PlaybookRun | null>>;
}

export function usePlaybookRunPolling({ view, queryClient, setActiveRun }: RunPollingArgs) {
  const [runLoadError, setRunLoadError] = useState("");
  const [runReloadToken, setRunReloadToken] = useState(0);

  useEffect(() => {
    if (view.mode !== "run-results") return;
    const runId = view.runId;
    let cancelled = false;
    let timer: number | undefined;
    setRunLoadError("");
    setActiveRun((current) => (current?.id === runId ? current : null));
    const tick = async () => {
      try {
        const res = await getPlaybookRun(runId);
        if (cancelled) return;
        setActiveRun(res.run);
        if (res.run.status === "pending" || res.run.status === "running") {
          timer = window.setTimeout(() => void tick(), 1200);
        } else {
          void queryClient.invalidateQueries({ queryKey: ["playbooks"] });
          void queryClient.invalidateQueries({ queryKey: ["playbook-runs"] });
        }
      } catch (error) {
        if (!cancelled) {
          setRunLoadError(error instanceof Error ? error.message : String(error));
        }
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [queryClient, runReloadToken, setActiveRun, view]);

  const retryRunLoad = useCallback(() => {
    setRunLoadError("");
    setRunReloadToken((current) => current + 1);
  }, []);

  return { runLoadError, retryRunLoad };
}
