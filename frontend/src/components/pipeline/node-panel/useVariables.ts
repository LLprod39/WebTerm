import { useMemo } from "react";

export type VariableOccurrence = {
  raw: string;
  name: string;
  start: number;
  end: number;
};

export type VariableTag = {
  name: string;
  occurrences: VariableOccurrence[];
};

const VARIABLE_TOKEN_REGEX = /(?:\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}|\{([A-Za-z_][A-Za-z0-9_.-]*)\})/g;

export function extractVariables(value: string): VariableTag[] {
  const source = value || "";
  const seen = new Map<string, VariableTag>();
  let match: RegExpExecArray | null;

  while ((match = VARIABLE_TOKEN_REGEX.exec(source)) !== null) {
    const name = match[1] || match[2];
    if (!name) continue;

    const entry = seen.get(name) || { name, occurrences: [] };
    entry.occurrences.push({
      raw: match[0],
      name,
      start: match.index,
      end: match.index + match[0].length,
    });
    seen.set(name, entry);
  }

  return [...seen.values()];
}

export function useVariables(value: string) {
  return useMemo(() => extractVariables(value), [value]);
}
