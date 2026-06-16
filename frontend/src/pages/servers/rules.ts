export function toJson(text: string): Record<string, string> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  return JSON.parse(trimmed) as Record<string, string>;
}

export function toUnknownJson(text: string): Record<string, unknown> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  return JSON.parse(trimmed) as Record<string, unknown>;
}

export function jsonText(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function uniqueLines(lines: string[]): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const line of lines) {
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(line);
  }
  return next;
}

export function getServerEnvironmentVars(networkConfig: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!networkConfig || typeof networkConfig !== "object") return {};

  const fromEnvVars =
    networkConfig.env_vars && typeof networkConfig.env_vars === "object"
      ? (networkConfig.env_vars as Record<string, unknown>)
      : {};
  const fromEnvironment =
    networkConfig.environment && typeof networkConfig.environment === "object"
      ? (networkConfig.environment as Record<string, unknown>)
      : {};

  return Object.fromEntries(
    Object.entries({ ...fromEnvVars, ...fromEnvironment }).map(([key, value]) => [key, String(value ?? "")]),
  );
}

export function mergeEnvironments(...layers: Array<Record<string, string>>) {
  return Object.assign({}, ...layers);
}

export function formatScopedRulesPreview(layers: Array<{ label: string; value: string }>) {
  const sections = layers
    .map(({ label, value }) => ({ label, value: value.trim() }))
    .filter(({ value }) => Boolean(value))
    .map(({ label, value }) => `[${label}]\n${value}`);

  return sections.join("\n\n");
}
