/**
 * CodeMirror 6 wrapper for the GUI file editor.
 *
 * Features: syntax highlighting, line numbers, search (Ctrl-F),
 * bracket matching, folding, indent guides, dark theme.
 */

import { useEffect, useRef } from "react";
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, highlightSpecialChars } from "@codemirror/view";
import { EditorState, type Extension } from "@codemirror/state";
import { defaultKeymap, indentWithTab, history, historyKeymap } from "@codemirror/commands";
import {
  syntaxHighlighting,
  defaultHighlightStyle,
  bracketMatching,
  foldGutter,
  indentOnInput,
  HighlightStyle,
  syntaxTree,
} from "@codemirror/language";
import { linter, lintGutter, type Diagnostic } from "@codemirror/lint";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { tags } from "@lezer/highlight";

import { detectLanguageExt } from "./codeEditorLanguage";

/* ------------------------------------------------------------------ */
/*  Dark theme matching terminal palette                               */
/* ------------------------------------------------------------------ */

const darkTheme = EditorView.theme(
  {
    "&": {
      color: "hsl(var(--foreground))",
      backgroundColor: "transparent",
      fontSize: "13px",
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    },
    ".cm-content": { caretColor: "hsl(var(--info))", padding: "8px 0" },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "hsl(var(--info))" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
      backgroundColor: "hsl(var(--info) / 0.28) !important",
    },
    ".cm-activeLine": { backgroundColor: "hsl(var(--foreground) / 0.04)" },
    ".cm-gutters": {
      backgroundColor: "transparent",
      color: "hsl(var(--muted-foreground))",
      border: "none",
      paddingRight: "8px",
    },
    ".cm-activeLineGutter": { backgroundColor: "hsl(var(--foreground) / 0.04)", color: "hsl(var(--muted-foreground))" },
    ".cm-foldGutter": { color: "hsl(var(--muted-foreground))" },
    ".cm-lineNumbers .cm-gutterElement": { minWidth: "3ch" },
    ".cm-searchMatch": { backgroundColor: "hsl(var(--warning) / 0.25)", outline: "1px solid hsl(var(--warning) / 0.5)" },
    ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "hsl(var(--warning) / 0.38)" },
    ".cm-matchingBracket": { backgroundColor: "hsl(var(--success) / 0.2)", outline: "1px solid hsl(var(--success) / 0.4)" },
    ".cm-panels": { backgroundColor: "hsl(var(--surface-2))", color: "hsl(var(--foreground))" },
    ".cm-panel.cm-search": {
      backgroundColor: "hsl(var(--surface-2))",
      padding: "8px",
      "& input, & button": {
        backgroundColor: "hsl(var(--surface-0))",
        color: "hsl(var(--foreground))",
        border: "1px solid hsl(var(--border))",
        borderRadius: "4px",
        padding: "2px 6px",
        fontSize: "12px",
      },
      "& button:hover": { backgroundColor: "hsl(var(--secondary))" },
      "& label": { color: "hsl(var(--muted-foreground))", fontSize: "12px" },
    },
    ".cm-tooltip": {
      backgroundColor: "hsl(var(--surface-3))",
      border: "1px solid hsl(var(--border))",
      color: "hsl(var(--foreground))",
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

export interface CodeEditorDiagnostic {
  from: number;
  to: number;
  line: number;
  column: number;
  severity: Diagnostic["severity"];
  message: string;
}

interface CodeEditorProps {
  content: string;
  filename: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  onSave?: () => void;
  onDiagnosticsChange?: (diagnostics: CodeEditorDiagnostic[]) => void;
  ariaLabel?: string;
  className?: string;
}

export function CodeEditor({
  content,
  filename,
  readOnly = false,
  onChange,
  onSave,
  onDiagnosticsChange,
  ariaLabel,
  className,
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const contentRef = useRef(content);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onDiagnosticsChangeRef = useRef(onDiagnosticsChange);
  const diagnosticsEnabled = Boolean(onDiagnosticsChange);
  contentRef.current = content;
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  onDiagnosticsChangeRef.current = onDiagnosticsChange;

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
      EditorView.contentAttributes.of({ "aria-label": ariaLabel || filename }),
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
    if (langExt && diagnosticsEnabled) {
      extensions.push(
        lintGutter(),
        linter(
          (view) => {
            const diagnostics: Diagnostic[] = [];
            syntaxTree(view.state).iterate({
              enter(node) {
                if (!node.type.isError) return;
                diagnostics.push({
                  from: node.from,
                  to: node.to,
                  severity: "error",
                  message: "Syntax error",
                });
              },
            });
            onDiagnosticsChangeRef.current?.(
              diagnostics.map((diagnostic) => {
                const line = view.state.doc.lineAt(Math.min(diagnostic.from, view.state.doc.length));
                return {
                  ...diagnostic,
                  line: line.number,
                  column: diagnostic.from - line.from + 1,
                };
              }),
            );
            return diagnostics;
          },
          { delay: 150 },
        ),
      );
    }
    if (readOnly) extensions.push(EditorState.readOnly.of(true));

    const state = EditorState.create({ doc: contentRef.current, extensions });
    const view = new EditorView({ state, parent: containerRef.current });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [ariaLabel, diagnosticsEnabled, filename, readOnly]); // recreate when editor capabilities change

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
      className={`h-full w-full overflow-auto ${className ?? ""}`}
    />
  );
}
