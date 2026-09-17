import { useCallback, useEffect, useState } from "react";

import type { PipelineNode } from "@/lib/api";

import { parseJsonObjectText } from "./jsonSchemaUtils";
import { localize } from "./presentation";
import { useRouteRunDialogRequest } from "./useRouteRunDialogRequest";
import { useRunContextFields } from "./useRunContextFields";

type ManualTriggerOption = { node_id: string };

export function usePipelineRunDialogState({
  hasHydratedPipeline,
  lang,
  manualTriggerOptions,
  nodes,
  showClientValidationError,
}: {
  hasHydratedPipeline: boolean;
  lang: "en" | "ru";
  manualTriggerOptions: ManualTriggerOption[];
  nodes: PipelineNode[];
  showClientValidationError: () => boolean;
}) {
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [runTaskText, setRunTaskText] = useState("");
  const [runRequester, setRunRequester] = useState("");
  const [runTicketId, setRunTicketId] = useState("");
  const [runAdvancedOpen, setRunAdvancedOpen] = useState(false);
  const [runContextText, setRunContextText] = useState("{}");
  const [runContextError, setRunContextError] = useState<string | null>(null);
  const [runEntryNodeId, setRunEntryNodeId] = useState("");
  const [runTriggerError, setRunTriggerError] = useState<string | null>(null);

  const { runtimeContextFields, handleApplyRuntimeContextFields, validateRuntimeContextFields } = useRunContextFields({
    lang,
    nodes,
    runContextText,
    setRunContextText,
    setRunContextError,
    setRunAdvancedOpen,
  });

  useEffect(() => {
    if (manualTriggerOptions.length === 1) {
      setRunEntryNodeId((current) => current || manualTriggerOptions[0].node_id);
      setRunTriggerError(null);
      return;
    }
    if (runEntryNodeId && manualTriggerOptions.some((item) => item.node_id === runEntryNodeId)) {
      return;
    }
    setRunEntryNodeId("");
  }, [manualTriggerOptions, runEntryNodeId]);

  useRouteRunDialogRequest({ hasHydratedPipeline, manualTriggerOptions, setRunDialogOpen, setRunEntryNodeId });

  const handleOpenRunDialog = useCallback(() => {
    setRunTriggerError(null);
    if (manualTriggerOptions.length === 1) {
      setRunEntryNodeId(manualTriggerOptions[0].node_id);
    }
    setRunDialogOpen(true);
  }, [manualTriggerOptions]);

  const resetRunDialog = useCallback(() => {
    setRunDialogOpen(false);
    setRunTaskText("");
    setRunRequester("");
    setRunTicketId("");
    setRunAdvancedOpen(false);
    setRunContextText("{}");
    setRunContextError(null);
    setRunEntryNodeId("");
    setRunTriggerError(null);
  }, []);

  const prepareManualRunRequest = useCallback((): { context: Record<string, unknown>; entryNodeId: string } | null => {
    if (!manualTriggerOptions.length) {
      setRunTriggerError(
        localize(
          lang,
          "У этого пайплайна нет ручного триггера. Используйте webhook или триггер расписания.",
          "This pipeline has no manual trigger. Use its webhook or schedule trigger instead.",
        ),
      );
      return null;
    }
    const parsedContext = parseJsonObjectText(runContextText);
    if (parsedContext.error) {
      setRunContextError(parsedContext.error);
      return null;
    }
    if (!validateRuntimeContextFields(parsedContext.value || {})) return null;
    setRunContextError(null);
    if (showClientValidationError()) return null;

    const context: Record<string, unknown> = {
      ...(parsedContext.value || {}),
    };
    if (runTaskText.trim()) context.task = runTaskText.trim();
    if (runRequester.trim()) context.requester = runRequester.trim();
    if (runTicketId.trim()) context.ticket_id = runTicketId.trim();
    const selectedEntryNodeId =
      manualTriggerOptions.length === 1
        ? manualTriggerOptions[0].node_id
        : runEntryNodeId.trim();
    if (!selectedEntryNodeId) {
      setRunTriggerError(localize(lang, "Выберите ручной триггер для запуска.", "Select the manual trigger that should start this run."));
      return null;
    }
    setRunTriggerError(null);

    return { context, entryNodeId: selectedEntryNodeId };
  }, [
    lang,
    manualTriggerOptions,
    runContextText,
    runEntryNodeId,
    runRequester,
    runTaskText,
    runTicketId,
    showClientValidationError,
    validateRuntimeContextFields,
  ]);

  return {
    handleApplyRuntimeContextFields,
    handleOpenRunDialog,
    prepareManualRunRequest,
    resetRunDialog,
    runAdvancedOpen,
    runContextError,
    runContextText,
    runDialogOpen,
    runEntryNodeId,
    runRequester,
    runTaskText,
    runTicketId,
    runTriggerError,
    runtimeContextFields,
    setRunAdvancedOpen,
    setRunContextError,
    setRunContextText,
    setRunDialogOpen,
    setRunEntryNodeId,
    setRunRequester,
    setRunTaskText,
    setRunTicketId,
    setRunTriggerError,
  };
}
