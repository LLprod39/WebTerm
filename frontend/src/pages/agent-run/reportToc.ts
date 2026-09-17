export interface ReportTocItem {
  depth: number;
  label: string;
  id: string;
  line: number;
}

const SHORT_REPORT_CHARS = 1200;

function slug(value: string) {
  return value
    .toLocaleLowerCase("ru-RU")
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "section";
}

export function extractReportToc(markdown: string): ReportTocItem[] {
  const seen = new Map<string, number>();
  const result: ReportTocItem[] = [];
  let fenced = false;
  markdown.split(/\r?\n/).forEach((line, index) => {
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced;
      return;
    }
    if (fenced) return;
    const match = /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!match) return;
    const label = match[2].replace(/[*_`~]/g, "").trim();
    const base = slug(label);
    const count = (seen.get(base) || 0) + 1;
    seen.set(base, count);
    result.push({ depth: match[1].length, label, id: count === 1 ? base : `${base}-${count}`, line: index + 1 });
  });
  return result;
}

export function shouldShowReportToc(markdown: string, toc: ReportTocItem[] = extractReportToc(markdown)): boolean {
  const top = toc.filter((item) => item.depth <= 2);
  return top.length > 3 && markdown.trim().length > SHORT_REPORT_CHARS;
}
