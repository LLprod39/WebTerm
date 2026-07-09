/**
 * Detect text filenames / paths in terminal lines (ls, ls -l, plain output).
 */

import type { IBufferRange, ILink, ILinkProvider, Terminal } from "@xterm/xterm";

/** Extensions treated as editable text files in the SSH terminal. */
export const TERMINAL_TEXT_FILE_EXTENSIONS = new Set([
  "py",
  "txt",
  "yml",
  "yaml",
  "json",
  "sh",
  "bash",
  "md",
  "toml",
  "ini",
  "cfg",
  "conf",
  "env",
  "js",
  "ts",
  "tsx",
  "jsx",
  "xml",
  "sql",
  "go",
  "rs",
  "rb",
  "php",
  "java",
  "kt",
  "c",
  "h",
  "cpp",
  "hpp",
  "cs",
  "vue",
  "svelte",
  "css",
  "scss",
  "less",
  "html",
  "htm",
  "properties",
  "service",
  "timer",
  "dockerfile",
  "gitignore",
  "editorconfig",
  "log",
]);

const EXT_PATTERN = Array.from(TERMINAL_TEXT_FILE_EXTENSIONS).join("|");

/**
 * Match bare names, relative paths, and absolute/home paths ending with a text extension.
 * Examples: app.py, ./cfg.yml, src/main.py, /etc/nginx/nginx.conf, ~/proj/a.py
 *
 * Absolute/home prefixes are a single alternative so `~/proj/x.py` is not
 * mis-read as `/proj/x.py` after the tilde.
 */
const FILE_PATH_RE = new RegExp(
  `(?<![\\w@+])(` +
    `(?:~/|/)(?:[\\w@+.,$-]+/)*[\\w@+.,$-]+\\.(?:${EXT_PATTERN})` +
    `|` +
    `(?:\\./|\\.\\./)?(?:[\\w@+.,$-]+/)*[\\w@+.,$-]+\\.(?:${EXT_PATTERN})` +
    `)(?![\\w.-])`,
  "gi",
);

/** ls -l: permissions block then remainder of line (name and optional " -> target"). */
const LS_LONG_TAIL_RE = new RegExp(
  `^[dl-][rwx-]{9}\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+(.+?)\\s*$`,
);

const PROMPT_CWD_RE =
  /(?:^|\]|\)|\s)(?:[\w.-]+@)?[\w.-]+:([/~][^\s$#]+)[$#]\s*$/;

const ANSI_ESCAPE = String.fromCharCode(27);
const ANSI_SEQUENCE_RE = new RegExp(`${ANSI_ESCAPE}\\[[0-9;?]*[ -/]*[@-~]`, "g");

export function stripAnsi(text: string): string {
  return text.replace(ANSI_SEQUENCE_RE, "").replace(/\r/g, "");
}

export function parsePromptCwd(line: string): string | null {
  const clean = stripAnsi(line).trim();
  const match = clean.match(PROMPT_CWD_RE);
  if (!match?.[1]) return null;
  return match[1].trim() || "/";
}

export function hasTextExtension(filename: string): boolean {
  const base = filename.split("/").pop() || filename;
  const lowerBase = base.toLowerCase();
  // Special filenames without a classic extension
  if (lowerBase === "dockerfile" || lowerBase === ".gitignore" || lowerBase === ".editorconfig") {
    return true;
  }
  const dot = base.lastIndexOf(".");
  if (dot <= 0) return false;
  const ext = base.slice(dot + 1).toLowerCase();
  return TERMINAL_TEXT_FILE_EXTENSIONS.has(ext);
}

/**
 * Extract text file paths/names from a terminal line.
 * Prefers full path tokens (src/app.py, /etc/a.conf) over bare basenames.
 */
export function extractTextFilenames(line: string): string[] {
  const clean = stripAnsi(line);
  if (!clean.trim()) return [];

  const names = new Set<string>();
  const longMatch = clean.match(LS_LONG_TAIL_RE);
  if (longMatch?.[1]) {
    const tail = longMatch[1].trim();
    // Prefer symlink target when it looks like a text file path
    const arrowParts = tail.split(/\s+->\s+/);
    const left = arrowParts[0]?.trim() || tail;
    const right = arrowParts[1]?.trim();
    if (right && hasTextExtension(right)) {
      names.add(right);
      return Array.from(names);
    }
    if (hasTextExtension(left)) {
      names.add(left);
    }
    return Array.from(names);
  }

  let match: RegExpExecArray | null;
  const re = new RegExp(FILE_PATH_RE.source, FILE_PATH_RE.flags);
  while ((match = re.exec(clean)) !== null) {
    const name = match[1];
    if (name && hasTextExtension(name)) {
      names.add(name);
    }
  }
  return Array.from(names);
}

/**
 * Join a relative path with remote cwd. Expands a leading `~` using homePath when provided.
 */
export function joinRemotePath(cwd: string, filename: string, homePath = ""): string {
  const name = filename.trim();
  if (!name) return name;

  const home = (homePath || "").replace(/\/+$/, "");
  const expandTilde = (value: string): string => {
    if (value === "~") return home || value;
    if (value.startsWith("~/")) return home ? `${home}/${value.slice(2)}` : value;
    return value;
  };

  const expandedName = expandTilde(name);
  if (expandedName.startsWith("/")) return expandedName;

  const baseRaw = expandTilde((cwd || "/").trim() || "/");
  const base = baseRaw.replace(/\/+$/, "") || "";
  // Relative segments like ./foo or ../bar
  if (!base || base === "/") return `/${expandedName.replace(/^\.\//, "")}`;
  if (expandedName.startsWith("./")) return `${base}/${expandedName.slice(2)}`;
  return `${base}/${expandedName}`;
}

export function createTerminalFileLinkProvider(
  term: Terminal,
  options: {
    getCwd: () => string;
    getHomePath?: () => string;
    onOpen: (absolutePath: string, filename: string) => void;
    enabled?: () => boolean;
  },
): ILinkProvider {
  return {
    provideLinks(bufferLineNumber, callback) {
      if (options.enabled && !options.enabled()) {
        callback(undefined);
        return;
      }
      const line = term.buffer.active.getLine(bufferLineNumber);
      if (!line) {
        callback(undefined);
        return;
      }
      const text = line.translateToString(true);
      const filenames = extractTextFilenames(text);
      if (!filenames.length) {
        callback(undefined);
        return;
      }

      const links: ILink[] = [];
      const clean = stripAnsi(text);
      // Prefer longer matches first so "src/app.py" wins over accidental shorter tokens.
      const ordered = [...filenames].sort((a, b) => b.length - a.length);
      const usedRanges: Array<{ start: number; end: number }> = [];

      for (const filename of ordered) {
        const start = findFilenameIndex(clean, filename, usedRanges);
        if (start < 0) continue;
        const end = start + filename.length;
        usedRanges.push({ start, end });
        const range: IBufferRange = {
          start: { x: start + 1, y: bufferLineNumber },
          end: { x: end, y: bufferLineNumber },
        };
        links.push({
          text: filename,
          range,
          activate: () => {
            const cwd = options.getCwd();
            const home = options.getHomePath?.() || "";
            const absolutePath = joinRemotePath(cwd, filename, home);
            options.onOpen(absolutePath, filename);
          },
        });
      }

      callback(links.length ? links : undefined);
    },
  };
}

function rangesOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart < bEnd && bStart < aEnd;
}

function findFilenameIndex(
  line: string,
  filename: string,
  usedRanges: Array<{ start: number; end: number }> = [],
): number {
  let idx = 0;
  const isPathToken = filename.startsWith("/") || filename.startsWith("~") || filename.includes("/");
  while (idx < line.length) {
    const found = line.indexOf(filename, idx);
    if (found < 0) return -1;
    const end = found + filename.length;
    const before = found > 0 ? line[found - 1] : "";
    const after = end < line.length ? line[end] : "";

    // Path tokens may follow punctuation/whitespace; bare names must not sit inside a longer token.
    const leftOk = isPathToken
      ? found === 0 || !/[\w@+]/.test(before)
      : found === 0 || !/[\w@+./-]/.test(before);
    const rightOk = end >= line.length || !/[\w.-]/.test(after);
    const free = !usedRanges.some((r) => rangesOverlap(found, end, r.start, r.end));

    if (leftOk && rightOk && free) {
      return found;
    }
    idx = found + 1;
  }
  return -1;
}
