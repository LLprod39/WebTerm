import { api } from "./client";
export interface TerminalPreferences {
  font_size: number;
  font_family: string;
  line_height: number;
  cursor_style: "block" | "bar" | "underline";
  cursor_blink: boolean;
  scrollback: number;
  intercept_editors: boolean;
}
export const terminalPreferencesApi = {
  get: (signal?: AbortSignal) =>
    api.get<TerminalPreferences>("/api/terminal/preferences/", signal),
  update: (body: Partial<TerminalPreferences>) =>
    api.patch<TerminalPreferences>("/api/terminal/preferences/", body),
};
