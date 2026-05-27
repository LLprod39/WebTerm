/**
 * Detect text filenames in terminal lines (ls, ls -l, plain output).
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

const FILENAME_RE = new RegExp(
  `(?<![\\w./-])([\\w@+.,-]+\\.(?:${EXT_PATTERN}))(?![\\w.-])`,
  "gi",
);

/** ls -l: permissions block then filename at end (before optional " -> target"). */
const LS_LONG_TAIL_RE = new RegExp(
  `^[dl-][rwx-]{9}\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+\\S+\\s+(.+?)(?:\\s+->\\s+\\S+)?\\s*$`,
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

export function extractTextFilenames(line: string): string[] {
  const clean = stripAnsi(line);
  if (!clean.trim()) return [];

  const names = new Set<string>();
  const longMatch = clean.match(LS_LONG_TAIL_RE);
  if (longMatch?.[1]) {
    const tail = longMatch[1].trim();
    const base = tail.split(/\s+->\s+/)[0]?.trim() || tail;
    if (hasTextExtension(base)) {
      names.add(base);
    }
    return Array.from(names);
  }

  let match: RegExpExecArray | null;
  const re = new RegExp(FILENAME_RE.source, FILENAME_RE.flags);
  while ((match = re.exec(clean)) !== null) {
    const name = match[1];
    if (name && hasTextExtension(name)) {
      names.add(name);
    }
  }
  return Array.from(names);
}

export function hasTextExtension(filename: string): boolean {
  const base = filename.split("/").pop() || filename;
  const dot = base.lastIndexOf(".");
  if (dot <= 0) return false;
  const ext = base.slice(dot + 1).toLowerCase();
  return TERMINAL_TEXT_FILE_EXTENSIONS.has(ext);
}

export function joinRemotePath(cwd: string, filename: string): string {
  const name = filename.trim();
  if (!name) return name;
  if (name.startsWith("/")) return name;
  const base = (cwd || "/").replace(/\/+$/, "") || "";
  if (!base || base === "/") return `/${name}`;
  return `${base}/${name}`;
}

export function createTerminalFileLinkProvider(
  term: Terminal,
  options: {
    getCwd: () => string;
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

      for (const filename of filenames) {
        const start = findFilenameIndex(clean, filename);
        if (start < 0) continue;
        const range: IBufferRange = {
          start: { x: start, y: bufferLineNumber },
          end: { x: start + filename.length, y: bufferLineNumber },
        };
        links.push({
          text: filename,
          range,
          activate: () => {
            const cwd = options.getCwd();
            const absolutePath = joinRemotePath(cwd, filename);
            options.onOpen(absolutePath, filename);
          },
        });
      }

      callback(links.length ? links : undefined);
    },
  };
}

function findFilenameIndex(line: string, filename: string): number {
  let idx = 0;
  while (idx < line.length) {
    const found = line.indexOf(filename, idx);
    if (found < 0) return -1;
    const before = found > 0 ? line[found - 1] : "";
    const after = found + filename.length < line.length ? line[found + filename.length] : "";
    if (!/[\w.-]/.test(before) && !/[\w.-]/.test(after)) {
      return found;
    }
    idx = found + 1;
  }
  return -1;
}
