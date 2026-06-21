import type { Extension } from "@codemirror/state";
import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";

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
    py: "Python",
    js: "JavaScript",
    ts: "TypeScript",
    tsx: "TSX",
    jsx: "JSX",
    json: "JSON",
    yaml: "YAML",
    yml: "YAML",
    toml: "TOML",
    sh: "Shell",
    bash: "Bash",
    zsh: "Zsh",
    conf: "Config",
    cfg: "Config",
    ini: "INI",
    md: "Markdown",
    txt: "Text",
    log: "Log",
    html: "HTML",
    css: "CSS",
    scss: "SCSS",
    xml: "XML",
    sql: "SQL",
    dockerfile: "Dockerfile",
    rs: "Rust",
    go: "Go",
    c: "C",
    cpp: "C++",
    h: "C Header",
    java: "Java",
    rb: "Ruby",
    php: "PHP",
    nginx: "Nginx",
    service: "systemd",
  };
  return labels[ext] || "Plain text";
}
