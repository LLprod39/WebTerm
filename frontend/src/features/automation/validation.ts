import { ApiError } from "@/api/client";
import type { Issue, Validation } from "@/api/automation";

export function pipelineValidationError(error: unknown): Validation | null {
  if (
    !(error instanceof ApiError) ||
    !error.details ||
    typeof error.details !== "object"
  )
    return null;
  const payload = error.details as Record<string, unknown>;
  const errors = Array.isArray(payload.details)
    ? payload.details.filter((item): item is string => typeof item === "string")
    : [];
  const issues = Array.isArray(payload.issues)
    ? payload.issues.filter(
        (item): item is Issue =>
          !!item &&
          typeof item === "object" &&
          typeof item.message === "string",
      )
    : [];
  return errors.length || issues.length ? { ok: false, errors, issues } : null;
}
