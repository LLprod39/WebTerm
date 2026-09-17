import type { AiQuestionOption } from "./ai-types";

export interface ParsedAiQuestionPayload {
  qId: string;
  question: string;
  cmd?: string;
  exitCode?: number;
  source?: string;
  options: AiQuestionOption[];
  allowMultiple: boolean;
  freeTextAllowed: boolean;
  placeholder?: string;
}

function parseQuestionOptions(value: unknown): AiQuestionOption[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const parsed: AiQuestionOption[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const label = String((item as { label?: unknown }).label || "").trim();
    const valueText = String((item as { value?: unknown }).value || "").trim();
    const description = String((item as { description?: unknown }).description || "").trim();
    if (!label || !valueText) {
      continue;
    }
    const option: AiQuestionOption = {
      label,
      value: valueText,
      description: description || undefined,
    };
    parsed.push(option);
    if (parsed.length >= 8) {
      break;
    }
  }
  return parsed;
}

export function parseAiQuestionPayload(payload: Record<string, unknown>): ParsedAiQuestionPayload {
  const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;
  return {
    qId: String(payload.q_id || ""),
    question: String(payload.question || ""),
    cmd: payload.cmd ? String(payload.cmd) : undefined,
    exitCode: Number.isFinite(exitCode) ? exitCode : undefined,
    source: payload.source ? String(payload.source) : undefined,
    options: parseQuestionOptions(payload.options),
    allowMultiple: Boolean(payload.allow_multiple),
    freeTextAllowed: payload.free_text_allowed === undefined ? true : Boolean(payload.free_text_allowed),
    placeholder: payload.placeholder ? String(payload.placeholder) : undefined,
  };
}
