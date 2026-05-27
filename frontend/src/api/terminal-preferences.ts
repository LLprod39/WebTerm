/**
 * src/api/terminal-preferences.ts — Terminal appearance preference API.
 */

import { apiFetch } from "@/lib/api";

export interface TerminalPrefs {
  theme_name: string;
  theme_colors: Record<string, string>;
  font_size: number;
  font_family: string;
  line_height: number;
  cursor_style: "block" | "bar" | "underline";
  cursor_blink: boolean;
  scrollback: number;
  intercept_editors: boolean;
}

export async function fetchTerminalPreferences(): Promise<TerminalPrefs> {
  return apiFetch<TerminalPrefs>("/api/terminal/preferences/");
}

export async function updateTerminalPreferences(
  data: Partial<TerminalPrefs>,
): Promise<TerminalPrefs> {
  return apiFetch<TerminalPrefs>("/api/terminal/preferences/", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function fetchCommandSuggestions(
  serverId: number,
  prefix: string,
): Promise<string[]> {
  const res = await apiFetch<{ suggestions: string[] }>(
    `/servers/api/${serverId}/command-suggestions/?q=${encodeURIComponent(prefix)}`,
  );
  return res.suggestions;
}
