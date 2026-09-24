/**
 * Fix common LLM markdown issues so tables/lists render reliably.
 * - GFM tables flattened onto one line
 * - Whitespace/tab "tables" without pipes
 * - Spurious separator-only rows (---) between every data row
 */

export function normalizeOperatorMarkdown(raw: string): string {
  const text = String(raw || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return text;

  return mapMarkdownProse(text, normalizeProse).trimEnd();
}

function normalizeProse(raw: string) {
  let text = raw;

  text = convertWhitespaceTables(text);
  text = fixFlattenedGfmTables(text);
  text = cleanGfmTableBlocks(text);
  text = ensureTableSeparator(text);
  text = text.replace(/^(#{1,6})([^\s#])/gm, "$1 $2");
  // Streamed sentences often arrive glued ("готово.Доступно", "алерт.#1", "78.nikitavm").
  // Do not touch version numbers (1.2.3) or domains (example.com).
  text = text.replace(/([.!?…])(?=[А-ЯЁA-Z#@])/g, "$1 ");
  text = text.replace(/(?<=[\dа-яёА-ЯЁ)])\.([a-z])/g, ". $1");
  text = text.replace(/([.!?…])\s+([-*•])\s+/g, "$1\n$2 ");
  text = liftInlineMetrics(text);
  text = breakDenseProse(text);
  text = text.replace(/\n{3,}/g, "\n\n");
  return text;
}

/**
 * Turn a single huge paragraph into scannable blocks: paragraph breaks on
 * topic shifts (alerts, metrics, SSH, questions) so chat does not look like a log dump.
 */
function breakDenseProse(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((block) => breakLongParagraph(block))
    .join("\n\n");
}

/** Split sentences without breaking decimals (5.8), versions (1.2.3), or domains (a.b). */
function splitSentences(text: string): string[] {
  const parts: string[] = [];
  let buf = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    buf += ch;
    if (!/[.!?…]/.test(ch)) continue;
    const prev = text[i - 1] || "";
    const next = text[i + 1] || "";
    if (ch === "." && /\d/.test(prev) && /\d/.test(next)) continue;
    if (ch === "." && /[A-Za-z]/.test(prev) && /[A-Za-z]/.test(next)) continue;
    parts.push(buf.trim());
    buf = "";
    while (text[i + 1] === " ") i += 1;
  }
  if (buf.trim()) parts.push(buf.trim());
  return parts.filter(Boolean);
}

function breakLongParagraph(para: string): string {
  const trimmed = para.trim();
  if (!trimmed || trimmed.length < 200) return para;
  if (trimmed.includes("\n")) return para;
  if (/^\s*[`|#>-]/.test(trimmed) || /^\s*\d+\.\s/.test(trimmed)) return para;

  const sentences = splitSentences(trimmed);
  if (sentences.length < 3) return para;

  const out: string[] = [];
  let buf = "";
  for (const s of sentences) {
    const topicShift =
      /^(alert|алерт|ssh|cpu|ram|disk|диск|ip\b|скажи|что\b|ошиб|error|не удалось|healthy|unreachable|снимок|метрик)/i.test(
        s,
      ) ||
      /\b(CPU|RAM|SSH|disk_percent|unreachable)\b/.test(s) ||
      /\?\s*$/.test(s);
    if (buf && (topicShift || buf.length > 140)) {
      out.push(buf.trim());
      buf = s;
    } else {
      buf = buf ? `${buf} ${s}` : s;
    }
  }
  if (buf) out.push(buf.trim());
  return out.length > 1 ? out.join("\n\n") : para;
}

/** Pull trailing "CPU x%, RAM y%, disk z%" clauses onto their own bullet lines. */
function liftInlineMetrics(text: string): string {
  return text.replace(
    /([.!?…:])\s*((?:CPU|RAM)\s+\d+(?:\.\d+)?%\s*,\s*(?:CPU|RAM)\s+\d+(?:\.\d+)?%(?:\s*,\s*(?:диск|Disk|disk)\s+[\d\s./()%A-Za-z-]{0,60})?)\s*([.!?…])/gi,
    (_m, end: string, metrics: string, stop: string) => {
      const parts = metrics
        .split(/,\s+(?=(?:CPU|RAM|диск|Disk|disk)\b)/i)
        .map((p) => p.trim())
        .filter(Boolean);
      if (parts.length < 2) return `${end} ${metrics.trim()}${stop}`;
      return `${end}\n\n${parts.map((p) => `- ${p}`).join("\n")}\n\n`;
    },
  );
}

/** Drop markdown table blocks from text (when we already render structured tables). */
export function stripMarkdownTables(raw: string): string {
  const text = String(raw || "").replace(/\r\n/g, "\n");
  return mapMarkdownProse(text, stripMarkdownTablesFromProse).trim();
}

function stripMarkdownTablesFromProse(raw: string): string {
  const lines = raw.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1] || "";
    if (
      (isPipeTableRow(line) || isWsTableRow(line)) &&
      (isPipeSeparator(next) || isWsSeparator(next) || isPipeTableRow(next) || isWsTableRow(next))
    ) {
      // skip header + following table-ish lines
      i += 1;
      while (i < lines.length && (isPipeTableRow(lines[i]) || isWsTableRow(lines[i]) || isPipeSeparator(lines[i]) || isWsSeparator(lines[i]) || lines[i].trim() === "")) {
        // stop blank line run if next is prose? keep one blank after table
        if (lines[i].trim() === "") {
          const look = lines[i + 1] || "";
          if (!isPipeTableRow(look) && !isWsTableRow(look) && !isPipeSeparator(look) && !isWsSeparator(look)) {
            i += 1;
            break;
          }
        }
        i += 1;
      }
      if (out.length && out[out.length - 1].trim() !== "") out.push("");
      continue;
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n");
}

type MarkdownSegment = { protected: boolean; value: string };

/**
 * Run repair rules only over prose. Commands, logs and examples inside fenced
 * or inline code must remain byte-for-byte stable while the answer streams.
 */
function mapMarkdownProse(raw: string, transform: (value: string) => string) {
  const segments: MarkdownSegment[] = [];
  const lines = raw.match(/[^\n]*(?:\n|$)/g) || [];
  let prose = "";
  let code = "";
  let fence: { char: "`" | "~"; length: number } | null = null;

  const flushProse = () => {
    if (!prose) return;
    segments.push({ protected: false, value: prose });
    prose = "";
  };
  const flushCode = () => {
    if (!code) return;
    segments.push({ protected: true, value: code });
    code = "";
  };

  for (const line of lines) {
    if (!line) continue;
    const withoutNewline = line.endsWith("\n") ? line.slice(0, -1) : line;
    if (!fence) {
      const opening = withoutNewline.match(/^\s*(`{3,}|~{3,})/);
      if (!opening) {
        prose += line;
        continue;
      }
      flushProse();
      const marker = opening[1];
      fence = { char: marker[0] as "`" | "~", length: marker.length };
      code += line;
      continue;
    }

    code += line;
    const escaped = fence.char === "`" ? "`" : "~";
    const closing = new RegExp(`^\\s*${escaped}{${fence.length},}\\s*$`);
    if (closing.test(withoutNewline)) {
      fence = null;
      flushCode();
    }
  }
  flushProse();
  flushCode();

  return segments
    .map((segment) => (segment.protected ? segment.value : mapInlineCode(segment.value, transform)))
    .join("");
}

function mapInlineCode(raw: string, transform: (value: string) => string) {
  const protectedSpans: string[] = [];
  const masked = raw.replace(/(`+)([^\n]*?)\1/g, (match) => {
    const marker = `\uE100${protectedSpans.length}\uE101`;
    protectedSpans.push(match);
    return marker;
  });
  const transformed = transform(masked);
  return transformed.replace(/\uE100(\d+)\uE101/g, (_match, index: string) => {
    return protectedSpans[Number(index)] ?? "";
  });
}

const isSepCell = (c: string) => /^:?-{2,}:?$/.test(c.replace(/\s/g, ""));

/**
 * Convert tab/multi-space separated tables into GFM.
 * Also drops pure --- separator rows that LLM inserts between every data row.
 */
function convertWhitespaceTables(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    // Find a run of ws-table-looking lines
    if (!isWsTableRow(lines[i]) && !isWsSeparator(lines[i])) {
      out.push(lines[i]);
      i += 1;
      continue;
    }

    // Need at least header + one data-ish line ahead
    const start = i;
    const block: string[] = [];
    while (i < lines.length && (isWsTableRow(lines[i]) || isWsSeparator(lines[i]))) {
      block.push(lines[i]);
      i += 1;
    }

    // Filter out pure separator rows from block for column detection
    const dataLines = block.filter((l) => !isWsSeparator(l));
    if (dataLines.length < 2) {
      out.push(...block);
      continue;
    }

    const rows = dataLines.map(splitWsRow);
    const colCount = modeLength(rows.map((r) => r.length));
    if (colCount < 2 || colCount > 12) {
      out.push(...block);
      continue;
    }

    // Normalize row widths
    const normalized = rows
      .map((r) => {
        if (r.length === colCount) return r;
        if (r.length > colCount) return r.slice(0, colCount);
        // skip junk short rows that are all ---
        if (r.every(isSepCell)) return null;
        while (r.length < colCount) r.push("");
        return r;
      })
      .filter((r): r is string[] => Boolean(r));

    if (normalized.length < 2) {
      out.push(...block);
      continue;
    }

    // If first row looks like separator, skip
    let header = normalized[0];
    let bodyStart = 1;
    if (header.every(isSepCell) && normalized.length > 2) {
      header = normalized[1];
      bodyStart = 2;
    }

    const body = normalized.slice(bodyStart).filter((r) => !r.every(isSepCell));
    if (!body.length) {
      out.push(...block);
      continue;
    }

    out.push("| " + header.join(" | ") + " |");
    out.push("| " + header.map(() => "---").join(" | ") + " |");
    for (const row of body) {
      out.push("| " + row.join(" | ") + " |");
    }
    // preserve blank after block if original had one — already handled by outer loop
  }

  // If we didn't convert anything useful, still try to clean --- lines between pipe tables
  return out.join("\n");
}

function splitWsRow(line: string): string[] {
  // Prefer tabs, else 2+ spaces
  if (line.includes("\t")) {
    return line.split("\t").map((c) => c.trim()).filter((c) => c.length > 0);
  }
  return line
    .trim()
    .split(/\s{2,}|\s\|\s/)
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
}

function isWsTableRow(line: string): boolean {
  const t = line.trim();
  if (!t || t.startsWith("#") || t.startsWith(">") || t.startsWith("- ") || t.startsWith("* ")) return false;
  if (isPipeTableRow(t)) return false;
  // at least 3 columns of multi-space or tab separated content
  if (t.includes("\t")) {
    return t.split("\t").filter((c) => c.trim()).length >= 3;
  }
  // "id  name  host" style
  const parts = t.split(/\s{2,}/).filter(Boolean);
  if (parts.length >= 3) return true;
  // single spaces but looks like: "3 lunix 172.25.173.251 22 — false"
  const single = t.split(/\s+/);
  if (single.length >= 4 && /^\d+$/.test(single[0])) return true;
  // header-like: "ID Имя Host Порт"
  if (single.length >= 4 && /^(id|имя|name|host|порт|port|теги|tags)/i.test(single[0])) return true;
  return false;
}

function isWsSeparator(line: string): boolean {
  const parts = splitWsRow(line);
  return parts.length >= 2 && parts.every(isSepCell);
}

function modeLength(lens: number[]): number {
  const counts = new Map<number, number>();
  for (const n of lens) counts.set(n, (counts.get(n) || 0) + 1);
  let best = 0;
  let bestN = 0;
  for (const [n, c] of counts) {
    if (c > bestN || (c === bestN && n > best)) {
      best = n;
      bestN = c;
    }
  }
  return best;
}

/**
 * LLM often emits:
 * | a | b | |---|---| | 1 | 2 | | 3 | 4 |
 * Rebuild into proper multiline GFM table.
 */
function fixFlattenedGfmTables(text: string): string {
  if (/\|\s*\n\s*\|?\s*:?-{3,}/.test(text)) {
    return text;
  }

  return text.replace(
    /(^|\n)((?:\|[^\n|]+){2,}\|(?:\s*\|[^\n|]+){2,}\|)/g,
    (full, lead: string, block: string) => {
      const cells = splitPipeRow(block);
      if (cells.length < 4) return full;

      const sepStart = cells.findIndex(isSepCell);
      if (sepStart <= 0) return full;
      const colCount = sepStart;
      if (colCount < 2 || colCount > 12) return full;

      let i = sepStart;
      while (i < cells.length && isSepCell(cells[i])) i += 1;

      const rows: string[][] = [];
      rows.push(cells.slice(0, colCount));
      for (; i + colCount <= cells.length; i += colCount) {
        const row = cells.slice(i, i + colCount);
        if (row.every(isSepCell)) continue;
        rows.push(row);
      }

      if (rows.length < 2) return full;

      const lines: string[] = [];
      lines.push("| " + rows[0].join(" | ") + " |");
      lines.push("| " + rows[0].map(() => "---").join(" | ") + " |");
      for (let r = 1; r < rows.length; r++) {
        lines.push("| " + rows[r].join(" | ") + " |");
      }
      return `${lead}${lines.join("\n")}`;
    },
  );
}

/** Remove repeated separator rows and junk from already multiline GFM tables. */
function cleanGfmTableBlocks(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    if (!isPipeTableRow(lines[i])) {
      out.push(lines[i]);
      i += 1;
      continue;
    }
    const block: string[] = [];
    while (i < lines.length && (isPipeTableRow(lines[i]) || isPipeSeparator(lines[i]))) {
      block.push(lines[i]);
      i += 1;
    }
    const cleaned = cleanOneGfmBlock(block);
    out.push(...cleaned);
  }
  return out.join("\n");
}

function cleanOneGfmBlock(block: string[]): string[] {
  if (block.length < 2) return block;
  const rows = block.map((line) => ({
    line,
    cells: splitPipeRow(line),
    sep: isPipeSeparator(line) || splitPipeRow(line).every(isSepCell),
  }));
  const header = rows[0];
  if (header.sep) return block;
  const colCount = header.cells.length;
  const body: string[][] = [];
  let sawSep = false;
  for (let i = 1; i < rows.length; i++) {
    if (rows[i].sep) {
      sawSep = true;
      continue; // only one separator needed
    }
    const cells = rows[i].cells;
    if (cells.every(isSepCell)) continue;
    if (cells.length === colCount) body.push(cells);
    else if (cells.length > colCount) body.push(cells.slice(0, colCount));
  }
  if (!body.length) return block;
  const out = [
    "| " + header.cells.join(" | ") + " |",
    "| " + header.cells.map(() => "---").join(" | ") + " |",
    ...body.map((r) => "| " + r.join(" | ") + " |"),
  ];
  return out;
}

function splitPipeRow(block: string): string[] {
  return block
    .split("|")
    .map((c) => c.trim())
    .filter((c, idx, arr) => {
      if (c === "" && (idx === 0 || idx === arr.length - 1)) return false;
      return true;
    });
}

function ensureTableSeparator(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    out.push(line);
    const next = lines[i + 1] || "";
    if (isPipeTableRow(line) && !isPipeSeparator(line) && isPipeTableRow(next) && !isPipeSeparator(next)) {
      // only inject if we don't already have a clean table (might be mid-body)
      // inject only when current looks like header (non-numeric first cell) and next starts with digit
      const currCells = splitPipeRow(line);
      const nextCells = splitPipeRow(next);
      const currLooksHeader = currCells.some((c) => /[A-Za-zА-Яа-я]/.test(c)) && !/^\d+$/.test(currCells[0] || "");
      const nextLooksData = /^\d+$/.test(nextCells[0] || "");
      if (currLooksHeader && nextLooksData) {
        const cols = currCells.length;
        if (cols >= 2) out.push("| " + Array(cols).fill("---").join(" | ") + " |");
      }
    }
  }
  return out.join("\n");
}

function isPipeTableRow(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.includes("|", 1);
}

function isPipeSeparator(line: string): boolean {
  const t = line.trim();
  if (!t.includes("|") && !t.includes("-")) return false;
  return /^\|?[\s:|-]+\|[\s:|-]*\|?$/.test(t) || splitPipeRow(t).every(isSepCell);
}
