import type { AgentConfig } from "@/lib/api";

export function buildAgentProfileSavePayload(
  form: Partial<AgentConfig>,
  canManageAiRouting: boolean,
): Partial<AgentConfig> {
  if (canManageAiRouting) return form;
  const payload = { ...form };
  delete payload.model;
  delete payload.provider_binding;
  return payload;
}
