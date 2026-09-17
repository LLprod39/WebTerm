import type { ITheme } from "@xterm/xterm";

export const DEFAULT_XTERM_THEME: ITheme = {
  background: "#0a0e14",
  foreground: "#a3be8c",
  cursor: "#22b8cf",
  selectionBackground: "#22b8cf33",
  black: "#1a1e24",
  red: "#e06c75",
  green: "#a3be8c",
  yellow: "#e5c07b",
  blue: "#61afef",
  magenta: "#c678dd",
  cyan: "#22b8cf",
  white: "#abb2bf",
  brightBlack: "#5c6370",
  brightRed: "#e06c75",
  brightGreen: "#a3be8c",
  brightYellow: "#e5c07b",
  brightBlue: "#61afef",
  brightMagenta: "#c678dd",
  brightCyan: "#22b8cf",
  brightWhite: "#ffffff",
};

export function normalizeTerminalFontFamily(fontFamily: string) {
  const trimmed = fontFamily.trim() || "JetBrains Mono";
  const quotedPrimary = /^[\w-]+\s+[\w\s-]+$/.test(trimmed) && !trimmed.includes(",") ? `"${trimmed}"` : trimmed;
  return `${quotedPrimary}, "Cascadia Mono", Consolas, "Courier New", monospace`;
}
