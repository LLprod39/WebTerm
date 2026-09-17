import { describe, expect, it } from "vitest";

import { collapseRepeatedCompactBlocks } from "./compactReportDisplay";
import { shouldShowReportToc } from "./reportToc";

describe("shouldShowReportToc", () => {
  it("hides toc for a short compact report", () => {
    const markdown = `# Логи не сняты

> Команды не запускались.

- Причина: docker.sock
- SSH до цели не проверялся

**Статус:** Ошибка
`;
    expect(shouldShowReportToc(markdown)).toBe(false);
  });

  it("shows toc for a long document with many headings", () => {
    const sections = ["Введение", "Факты", "Сервисы", "Сеть", "Итог"];
    const markdown = sections.map((name) => `## ${name}\n\n${"абзац ".repeat(80)}`).join("\n");
    expect(shouldShowReportToc(`# Отчёт\n\n${markdown}`)).toBe(true);
  });
});

describe("collapseRepeatedCompactBlocks", () => {
  it("keeps one copy when the model pasted the same report three times", () => {
    const duplicated = `# Логи на nikitavm не проверены — нет SSH/MCP
> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.
- Цель: только чтение логов контейнеров на \`nikitavm\`, без изменений- Итераций: 1- Проверен каталог dynamic tools- Итог агента: выполнить проверку нельзя
Дальше: подключить Ops SSH/MCP и повторить запрос.
**Статус:** ❌ Ошибка# Логи на nikitavm не проверены — нет SSH/MCP

> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.

- Цель: только чтение логов контейнеров на \`nikitavm\`, без изменений
- Итераций: 1
- Проверен каталог dynamic tools
- Итог агента: выполнить проверку нельзя

Дальше: подключить Ops SSH/MCP и повторить запрос.

**Статус:** ❌ Ошибка# Логи на nikitavm не проверены — нет SSH/MCP

> Live-чтение логов контейнеров недоступно: в сессии нет SSH/MCP из Ops-профиля.

- Цель: только чтение логов контейнеров на \`nikitavm\`, без изменений
- Итераций: 1
- Проверен каталог dynamic tools
- Итог агента: выполнить проверку нельзя

Дальше: подключить Ops SSH/MCP и повторить запрос.

**Статус:** ❌ Ошибка

## Контроль изменений
- Все обязательные post-change verification markers закрыты.

---
Outcome: partial — Final answer without tool evidence while tools were available
`;
    const result = collapseRepeatedCompactBlocks(duplicated);
    expect(result.match(/# Логи на nikitavm не проверены/g)).toHaveLength(1);
    expect(result.match(/\*\*Статус:\*\*/g)).toHaveLength(1);
    expect(result.match(/Live-чтение логов/g)).toHaveLength(1);
    expect(result).toContain("- Итераций: 1");
    expect(result).toContain("## Контроль изменений");
    expect(result).toContain("Outcome: partial");
    expect(result).not.toContain("Ошибка#");
  });
});
