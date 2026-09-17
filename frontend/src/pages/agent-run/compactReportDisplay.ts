/** Unstick and collapse compact agent reports the model pasted several times. */

function repairGluedCompactMarkdown(markdown: string): string {
  return markdown
    .replace(/(?<=[^\n#])(#{1,3}[ \t]+\S)/g, "\n$1")
    .replace(/(?<=[^\n])(\*\*Статус:\*\*)/g, "\n$1")
    .replace(/(?<=[^\n])(Дальше:)/g, "\n$1")
    .replace(/(?<=[^\n\s])(-[ \t]+)(?=[А-ЯA-Z«"`])/g, "\n$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function compactH1Blocks(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed
    .split(/(?=^# )/m)
    .map((block) => block.trim())
    .filter(Boolean);
}

function blockTitle(block: string): string {
  const first = block.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || "";
  return first.replace(/^#+\s*/, "").trim().toLocaleLowerCase("ru-RU");
}

function splitCompactAndTail(block: string): { compact: string; tail: string } {
  const match = /^(?:##\s+|---\s*$)/m.exec(block);
  if (!match || match.index == null) return { compact: block.trim(), tail: "" };
  return {
    compact: block.slice(0, match.index).trim(),
    tail: block.slice(match.index).trim(),
  };
}

function blockQuality(block: string): number[] {
  const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const bullets = lines.filter((line) => line.startsWith("- ")).length;
  const hasStatus = lines.some((line) => line.includes("**Статус:**")) ? 1 : 0;
  const hasQuote = lines.some((line) => line.startsWith(">")) ? 1 : 0;
  const glued = lines.some((line) => (line.match(/- /g) || []).length >= 2) ? 1 : 0;
  return [hasStatus, hasQuote, bullets, -glued, lines.length];
}

function qualityBetter(left: string, right: string): boolean {
  const a = blockQuality(left);
  const b = blockQuality(right);
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

export function collapseRepeatedCompactBlocks(markdown: string): string {
  const text = repairGluedCompactMarkdown(markdown);
  const blocks = compactH1Blocks(text);
  if (blocks.length < 2) return text;

  const parsed = blocks.map((block) => {
    const split = splitCompactAndTail(block);
    const compact = split.compact || block;
    return { title: blockTitle(compact), compact, tail: split.tail };
  });

  const counts = new Map<string, number>();
  for (const item of parsed) {
    if (!item.title) continue;
    counts.set(item.title, (counts.get(item.title) || 0) + 1);
  }
  let common = "";
  let copies = 0;
  for (const [title, count] of counts) {
    if (count > copies) {
      common = title;
      copies = count;
    }
  }
  if (copies < 2) return text;

  const same = parsed.filter((item) => item.title === common);
  let best = same[0].compact;
  for (const item of same) {
    if (qualityBetter(item.compact, best)) best = item.compact;
  }
  const tails: string[] = [];
  const seen = new Set<string>();
  for (const item of same) {
    const key = item.tail.replace(/\s+/g, " ").trim();
    if (item.tail && !seen.has(key)) {
      seen.add(key);
      tails.push(item.tail);
    }
  }
  const others = parsed.filter((item) => item.title !== common).map((item) => item.compact);
  return [best, ...others, ...tails].filter(Boolean).join("\n\n").trim();
}
