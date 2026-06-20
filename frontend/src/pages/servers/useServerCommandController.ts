import { useCallback, useState } from "react";

import { executeServerCommand, type FrontendServer } from "@/lib/api";

import { formatCommandOutput } from "./formatters";

type Translate = (key: string) => string;
type TranslateWithVars = (key: string, vars?: Record<string, string | number>) => string;

export function useServerCommandController(
  activeServer: FrontendServer | null,
  t: Translate,
  tr: TranslateWithVars,
) {
  const [execCommand, setExecCommand] = useState("hostname");
  const [execResult, setExecResult] = useState("");

  const resetResult = useCallback(() => {
    setExecResult("");
  }, []);

  const onExecuteCommand = useCallback(async () => {
    if (!activeServer || !execCommand.trim()) return;
    const response = await executeServerCommand(activeServer.id, execCommand, "");
    if (response.success) {
      setExecResult(formatCommandOutput(response.output));
    } else {
      setExecResult(tr("srv.execute_error", { error: response.error || t("srv.unknown_error") }));
    }
  }, [activeServer, execCommand, t, tr]);

  return {
    execCommand,
    execResult,
    onExecuteCommand,
    resetResult,
    setExecCommand,
  };
}

export type ServerCommandController = ReturnType<typeof useServerCommandController>;
