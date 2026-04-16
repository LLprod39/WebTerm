/**
 * CodeMirror 6 wrapper for the GUI file editor.
 *
 * Features: syntax highlighting, line numbers, search (Ctrl-F),
 * bracket matching, folding, indent guides, dark theme.
 */

import { useEffect, useRef, useCallback } from "react";
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, highlightSpecialChars } from "@codemirror/view";
import { EditorState, type Extension } from "@codemirror/state";
import { defaultKeymap, indentWithTab, history, historyKeymap, undo, redo } from "@codemirror/commands";
import { syntaxHighlighting, defaultHighlightStyle, bracketMatching, foldGutter, indentOnInput, HighlightStyle } from "@codemirror/language";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { tags } from "@lezer/highlight";

import { json } from "@codemirror/lang-json";
import { yaml } from "@codemirror/lang-yaml";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { xml } from "@codemirror/lang-xml";
import { markdown } from "@codemirror/lang-markdown";
import { sql } from "@codemirror/lang-sql";

/* ------------------------------------------------------------------ */
/*  Dark theme matching terminal palette                               */
/* ------------------------------------------------------------------ */

const darkTheme = EditorView.theme(
  {
    "&": {
      color: "#c9d1d9",
      backgroundColor: "transparent",
      fontSize: "13px",
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    },
    ".cm-content": { caretColor: "#58a6ff", padding: "8px 0" },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "#58a6ff" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
      backgroundColor: "#264f78 !important",
    },
    ".cm-activeLine": { backgroundColor: "#ffffff08" },
    ".cm-gutters": {
      backgroundColor: "transparent",
      color: "#484f58",
      border: "none",
      paddingRight: "8px",
    },
    ".cm-activeLineGutter": { backgroundColor: "#ffffff08", color: "#8b949e" },
    ".cm-foldGutter": { color: "#484f58" },
    ".cm-lineNumbers .cm-gutterElement": { minWidth: "3ch" },
    ".cm-searchMatch": { backgroundColor: "#e2c08d40", outline: "1px solid #e2c08d80" },
    ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "#e2c08d60" },
    ".cm-matchingBracket": { backgroundColor: "#17e5e633", outline: "1px solid #17e5e666" },
    ".cm-panels": { backgroundColor: "#161b22", color: "#c9d1d9" },
    ".cm-panel.cm-search": {
      backgroundColor: "#161b22",
      padding: "8px",
      "& input, & button": {
        backgroundColor: "#0d1117",
        color: "#c9d1d9",
        border: "1px solid #30363d",
        borderRadius: "4px",
        padding: "2px 6px",
        fontSize: "12px",
      },
      "& button:hover": { backgroundColor: "#21262d" },
      "& label": { color: "#8b949e", fontSize: "12px" },
    },
    ".cm-tooltip": {
      backgroundColor: "#1c2128",
      border: "1px solid #30363d",
      color: "#c9d1d9",
    },
  },
  { dark: true },
);

const darkHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: "#ff7b72" },
  { tag: tags.operator, color: "#79c0ff" },
  { tag: tags.variableName, color: "#ffa657" },
  { tag: tags.propertyName, color: "#79c0ff" },
  { tag: tags.definition(tags.variableName), color: "#ffa657" },
  { tag: tags.string, color: "#a5d6ff" },
  { tag: tags.number, color: "#79c0ff" },
  { tag: tags.bool, color: "#79c0ff" },
  { tag: tags.null, color: "#79c0ff" },
  { tag: tags.comment, color: "#8b949e", fontStyle: "italic" },
  { tag: tags.typeName, color: "#ffa657" },
  { tag: tags.className, color: "#ffa657" },
  { tag: tags.function(tags.variableName), color: "#d2a8ff" },
  { tag: tags.tagName, color: "#7ee787" },
  { tag: tags.attributeName, color: "#79c0ff" },
  { tag: tags.attributeValue, color: "#a5d6ff" },
  { tag: tags.meta, color: "#8b949e" },
  { tag: tags.heading, color: "#79c0ff", fontWeight: "bold" },
  { tag: tags.link, color: "#58a6ff", textDecoration: "underline" },
  { tag: tags.escape, color: "#79c0ff" },
  { tag: tags.regexp, color: "#7ee787" },
]);

/* ------------------------------------------------------------------ */
/*  Language detection                                                  */
/* ------------------------------------------------------------------ */

const LANG_MAP: Record<string, () => Extension> = {
  json: () => json(),
  jsonc: () => json(),
  yaml: () => yaml(),
  yml: () => yaml(),
  py: () => python(),
  python: () => python(),
  js: () => javascript(),
  mjs: () => javascript(),
  cjs: () => javascript(),
  ts: () => javascript({ typescript: true }),
  tsx: () => javascript({ typescript: true, jsx: true }),
  jsx: () => javascript({ jsx: true }),
  html: () => html(),
  htm: () => html(),
  css: () => css(),
  scss: () => css(),
  xml: () => xml(),
  svg: () => xml(),
  md: () => markdown(),
  markdown: () => markdown(),
  sql: () => sql(),
};

export function detectLanguageExt(filename: string): Extension | null {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const factory = LANG_MAP[ext];
  return factory ? factory() : null;
}

export function getLanguageLabel(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const labels: Record<string, string> = {
    py: "Python", js: "JavaScript", ts: "TypeScript", tsx: "TSX", jsx: "JSX",
    json: "JSON", yaml: "YAML", yml: "YAML", toml: "TOML",
    sh: "Shell", bash: "Bash", zsh: "Zsh",
    conf: "Config", cfg: "Config", ini: "INI",
    md: "Markdown", txt: "Text", log: "Log",
    html: "HTML", css: "CSS", scss: "SCSS",
    xml: "XML", sql: "SQL", dockerfile: "Dockerfile",
    rs: "Rust", go: "Go", c: "C", cpp: "C++", h: "C Header",
    java: "Java", rb: "Ruby", php: "PHP",
    nginx: "Nginx", service: "systemd",
  };
  return labels[ext] || "Plain text";
}

/* ------------------------------------------------------------------ */
/*  React component                                                     */
/* ------------------------------------------------------------------ */

interface CodeEditorProps {
  content: string;
  filename: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  onSave?: () => void;
  className?: string;
}

export function CodeEditor({ content, filename, readOnly = false, onChange, onSave, className }: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;

  // Stable callback for dispatching undo/redo from outside
  const handleUndo = useCallback(() => { if (viewRef.current) undo(viewRef.current); }, []);
  const handleRedo = useCallback(() => { if (viewRef.current) redo(viewRef.current); }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    const langExt = detectLanguageExt(filename);
    const extensions: Extension[] = [
      lineNumbers(),
      highlightActiveLine(),
      highlightSpecialChars(),
      drawSelection(),
      bracketMatching(),
      foldGutter(),
      indentOnInput(),
      highlightSelectionMatches(),
      history(),
      darkTheme,
      syntaxHighlighting(darkHighlight),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      keymap.of([
        ...defaultKeymap,
        ...historyKeymap,
        ...searchKeymap,
        indentWithTab,
        {
          key: "Mod-s",
          run: () => { onSaveRef.current?.(); return true; },
        },
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          onChangeRef.current?.(update.state.doc.toString());
        }
      }),
    ];
    if (langExt) extensions.push(langExt);
    if (readOnly) extensions.push(EditorState.readOnly.of(true));

    const state = EditorState.create({ doc: content, extensions });
    const view = new EditorView({ state, parent: containerRef.current });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [filename, readOnly]); // recreate on file/lang change

  // Sync external content changes (e.g., reload)
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== content) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: content },
      });
    }
  }, [content]);

  return (
    <div
      ref={containerRef}
      data-undo={handleUndo}
      data-redo={handleRedo}
      className={`h-full w-full overflow-auto ${className ?? ""}`}
    />
  );
}
