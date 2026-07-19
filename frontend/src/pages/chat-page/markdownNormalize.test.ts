import { describe, expect, it } from "vitest";

import { normalizeOperatorMarkdown, stripMarkdownTables } from "./markdownNormalize";

describe("normalizeOperatorMarkdown", () => {
  it("rebuilds flattened GFM tables onto multiple lines", () => {
    const flat =
      "Список серверов\n\n| ID | Имя | Host | |-----|------|------| | 3 | lunix | 1.2.3.4 | | 4 | web | 1.2.3.5 |";
    const out = normalizeOperatorMarkdown(flat);
    expect(out).toContain("| ID | Имя | Host |");
    expect(out).toContain("| --- | --- | --- |");
    expect(out).toContain("| 3 | lunix | 1.2.3.4 |");
    expect(out).toContain("| 4 | web | 1.2.3.5 |");
    expect(out.split("\n").filter((l) => l.includes("|")).length).toBeGreaterThanOrEqual(4);
  });

  it("converts whitespace tables and drops --- separator rows between data", () => {
    const raw = [
      "Список серверов (всего 16)",
      "",
      "ID    Имя    Host    Порт    Теги    AI read-only",
      "3    lunix    172.25.173.251    22    —    false",
      "---    ---    ---    ---    ---    ---",
      "4    web-prod-01    172.25.173.251    22    —    false",
      "---    ---    ---    ---    ---    ---",
      "5    web-prod-02    172.25.173.251    22    —    false",
    ].join("\n");
    const out = normalizeOperatorMarkdown(raw);
    expect(out).toContain("| ID | Имя | Host | Порт | Теги | AI read-only |");
    expect(out).toContain("| 3 | lunix | 172.25.173.251 | 22 | — | false |");
    expect(out).toContain("| 4 | web-prod-01 | 172.25.173.251 | 22 | — | false |");
    // only one separator line in the whole table
    const sepLines = out.split("\n").filter((l) => /^\|\s*---/.test(l.trim()));
    expect(sepLines.length).toBe(1);
    // no body rows that are pure ---
    expect(out).not.toMatch(/\|\s*---\s*\|\s*---\s*\|\s*---\s*\|\s*lunix/);
  });

  it("inserts missing separator between header and body rows", () => {
    const md = "| A | B |\n| 1 | 2 |";
    const out = normalizeOperatorMarkdown(md);
    expect(out).toMatch(/\| A \| B \|\n\| --- \| --- \|\n\| 1 \| 2 \|/);
  });

  it("strips tables when structured UI is used", () => {
    const md = "Intro\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nOutro";
    const stripped = stripMarkdownTables(md);
    expect(stripped).toContain("Intro");
    expect(stripped).toContain("Outro");
    expect(stripped).not.toContain("| A | B |");
  });
});
