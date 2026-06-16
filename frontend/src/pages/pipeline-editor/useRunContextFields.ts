import { useCallback, useMemo } from "react";

import type { PipelineNode } from "@/lib/api";

import {
  buildRunContextTextWithPlaceholders,
  getMissingRunContextFields,
  getPipelineRuntimePlaceholders,
} from "./pipelineGraphUtils";
import { localize } from "./presentation";

export function useRunContextFields({
  lang,
  nodes,
  runContextText,
  setRunContextText,
  setRunContextError,
  setRunAdvancedOpen,
}: {
  lang: "en" | "ru";
  nodes: PipelineNode[];
  runContextText: string;
  setRunContextText: (value: string) => void;
  setRunContextError: (value: string | null) => void;
  setRunAdvancedOpen: (value: boolean) => void;
}) {
  const runtimeContextFields = useMemo(() => getPipelineRuntimePlaceholders(nodes), [nodes]);
  const handleApplyRuntimeContextFields = useCallback(() => {
    const nextContext = buildRunContextTextWithPlaceholders(runContextText, runtimeContextFields);
    if (nextContext.error) {
      setRunContextError(nextContext.error);
      setRunAdvancedOpen(true);
      return;
    }
    setRunContextText(nextContext.text);
    setRunContextError(null);
    setRunAdvancedOpen(true);
  }, [runContextText, runtimeContextFields, setRunAdvancedOpen, setRunContextError, setRunContextText]);

  const validateRuntimeContextFields = useCallback((context: Record<string, unknown>) => {
    const missingFields = getMissingRunContextFields(context, runtimeContextFields);
    if (!missingFields.length) return true;
    setRunContextError(localize(lang, `Заполните поля context: ${missingFields.join(", ")}`, `Fill context fields: ${missingFields.join(", ")}`));
    setRunAdvancedOpen(true);
    return false;
  }, [lang, runtimeContextFields, setRunAdvancedOpen, setRunContextError]);

  return { runtimeContextFields, handleApplyRuntimeContextFields, validateRuntimeContextFields };
}
