/**
 * Floating resizable/draggable window for editing remote files via SFTP.
 *
 * Uses CodeEditor (CodeMirror 6) for syntax highlighting.
 * Multi-tab support, Ctrl+S save, unsaved-changes guard.
 * Can be minimized to a small bar or maximized to fill screen.
 * Supports elevated (sudo) open/save when permission is denied.
 */

import { FileEditorView } from "./file-editor/FileEditorView";
import type { FileEditorModalProps } from "./file-editor/types";
import { useFileEditorController } from "./file-editor/useFileEditorController";

export type { FileEditorModalProps } from "./file-editor/types";

export function FileEditorModal(props: FileEditorModalProps) {
  const ctrl = useFileEditorController(props);
  if (!props.open) return null;
  return <FileEditorView {...ctrl} />;
}
