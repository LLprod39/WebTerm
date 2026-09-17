/* ------------------------------------------------------------------ */
/*  Types for floating remote file editor                               */
/* ------------------------------------------------------------------ */

export interface EditorTab {
  id: string;
  path: string;
  filename: string;
  content: string;
  originalContent: string;
  encoding: string;
  isNew: boolean;
  dirty: boolean;
  loading: boolean;
  error: string | null;
  elevated: boolean;
}

export type SudoPrompt =
  | { kind: "open"; tabId: string; path: string }
  | { kind: "save"; tabId: string; path: string }
  | null;

export type WindowMode = "normal" | "minimized" | "maximized";

export interface FileEditorModalProps {
  serverId: number;
  open: boolean;
  initialPath?: string | null;
  /** Prefer elevated open (e.g. intercept of `sudo nano …`). */
  initialElevated?: boolean;
  onClose: () => void;
}

export const DEFAULT_RECT = { x: 80, y: 60, w: 900, h: 560 };

let _tabSeq = 0;
export function nextTabId() {
  _tabSeq += 1;
  return `ftab_${_tabSeq}`;
}
