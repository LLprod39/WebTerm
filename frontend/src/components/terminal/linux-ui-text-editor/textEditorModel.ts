import { localize } from "@/lib/i18n";

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
}

export const RECENT_TEXT_FILES_STORAGE_KEY = "linux_ui_recent_text_files_v1";

export const TEXT_EDITOR_PRESET_PATHS = [
  "/etc/nginx/nginx.conf",
  "/etc/hosts",
  "/etc/fstab",
  "/etc/crontab",
  "/etc/ssh/sshd_config",
  "~/.bashrc",
  "/etc/environment",
];

let tabSeq = 0;

export function nextTabId() {
  tabSeq += 1;
  return `tab_${tabSeq}`;
}

export function filenameFromPath(filePath: string) {
  return filePath.split("/").pop() || filePath;
}

export function readRecentTextFiles() {
  try {
    const raw = window.localStorage.getItem(RECENT_TEXT_FILES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .slice(0, 8);
  } catch {
    return [];
  }
}

export function writeRecentTextFiles(paths: string[]) {
  try {
    window.localStorage.setItem(RECENT_TEXT_FILES_STORAGE_KEY, JSON.stringify(paths.slice(0, 8)));
  } catch {
    // localStorage can be unavailable in privacy-restricted browser contexts.
  }
}

export function getLanguageHint(filename: string, lang: string) {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
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
  return map[ext] || localize(lang, "Обычный текст", "Plain text");
}
