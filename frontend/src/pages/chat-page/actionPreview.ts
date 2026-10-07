import type { AssistantAction } from "@/api";

const EN_TOOL_SCHEMA_HINTS = [
  /^create a custom agent/i,
  /^launch an existing/i,
  /^create an? /i,
  /^run /i,
];

function looksLikeEnToolSchema(description: string) {
  const text = description.trim();
  if (!text) return true;
  return EN_TOOL_SCHEMA_HINTS.some((pattern) => pattern.test(text));
}

function hasCyrillic(text: string) {
  return /[а-яё]/i.test(text);
}

/** Human-readable action summary for cards and the context rail (RU fallback). */
export function formatActionCardDescription(
  action: AssistantAction,
  lang: "ru" | "en" | string,
): string {
  const description = String(action.description || "").trim();
  const input = (action.input || {}) as Record<string, unknown>;
  const type = String(action.action_type || "").trim();

  if (
    description &&
    !looksLikeEnToolSchema(description) &&
    (lang !== "ru" || hasCyrillic(description))
  ) {
    return description;
  }

  if (type === "agent.create" || type === "agent_create") {
    const name = String(input.name || action.title || "").trim();
    const goal = String(input.goal || input.description || "").trim();
    const goalShort = goal.length > 60 ? `${goal.slice(0, 57)}…` : goal;
    if (lang === "ru") {
      if (name && goalShort) return `Создать агента «${name}» · ${goalShort}`;
      if (name) return `Создать агента «${name}»`;
      return "Создать агента";
    }
    if (name && goalShort) return `Create agent “${name}” · ${goalShort}`;
    if (name) return `Create agent “${name}”`;
    return "Create agent";
  }

  if (type === "agent.run" || type === "agent_run") {
    const id = input.run_id ?? input.agent_id ?? input.id;
    if (lang === "ru") {
      return id != null && String(id).trim() ? `Запустить агента #${id}` : "Запустить агента";
    }
    return id != null && String(id).trim() ? `Run agent #${id}` : "Run agent";
  }

  if (description && lang !== "ru") return description;
  return description || action.title || type;
}

export function actionServerLabel(action: AssistantAction): string {
  const blast = action.blast_radius || {};
  if (Array.isArray(blast.server_names) && blast.server_names.length) {
    return String(blast.server_names[0]);
  }
  const input = (action.input || {}) as Record<string, unknown>;
  if (input.server_name) return String(input.server_name);
  if (input.server_id != null) return `#${input.server_id}`;
  return "";
}

export function actionCommandLine(action: AssistantAction): string {
  const dry = action.dry_run_preview || {};
  if (typeof dry.command === "string" && dry.command.trim()) return dry.command.trim();
  const input = (action.input || {}) as Record<string, unknown>;
  const cmd = input.command ?? input.cmd;
  if (typeof cmd === "string" && cmd.trim()) return cmd.trim();
  return "";
}

export function actionResultOutput(action: AssistantAction): string {
  const result = (action.result || {}) as Record<string, unknown>;
  const nested = (result.result && typeof result.result === "object" ? result.result : result) as Record<
    string,
    unknown
  >;
  const out =
    (typeof nested.output === "string" && nested.output) ||
    (typeof nested.stdout === "string" && nested.stdout) ||
    (typeof result.output === "string" && result.output) ||
    (typeof result.stdout === "string" && result.stdout) ||
    "";
  return String(out).trim();
}

export function actionTargetLabel(action: AssistantAction): string {
  const blast = (action.blast_radius || {}) as Record<string, unknown>;
  const serverNames = Array.isArray(blast.server_names)
    ? blast.server_names.map(String).filter(Boolean)
    : [];
  if (serverNames.length) return serverNames.join(", ");
  const input = (action.input || {}) as Record<string, unknown>;
  const explicit = input.server_name ?? input.target_name ?? input.target ?? input.project_name;
  if (explicit != null && String(explicit).trim()) return String(explicit);
  if (action.target_url) return action.target_url;
  return "";
}

/** One-line preview for the compact action chip in the message stream. */
export function actionPreviewLine(action: AssistantAction): string {
  const server = actionServerLabel(action);
  const cmd = actionCommandLine(action);
  const output = action.status === "completed" ? actionResultOutput(action) : "";
  const firstOut = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);

  if (cmd) {
    const cmdBit = `$ ${cmd.length > 72 ? `${cmd.slice(0, 72)}…` : cmd}`;
    return server ? `${server} · ${cmdBit}` : cmdBit;
  }
  if (firstOut) {
    const hint = firstOut.length > 80 ? `${firstOut.slice(0, 80)}…` : firstOut;
    return server ? `${server} · ${hint}` : hint;
  }
  return server || actionTargetLabel(action);
}
