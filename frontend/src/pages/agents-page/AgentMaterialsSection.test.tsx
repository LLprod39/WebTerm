import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentMaterialsSection } from "./AgentMaterialsSection";

const noop = vi.fn();

describe("AgentMaterialsSection", () => {
  it("explains the isolated shell material execution boundary", () => {
    render(
      <AgentMaterialsSection
        lang="ru"
        inputArtifacts={[{ kind: "script", name: "check.sh", content: "echo ok" }]}
        activeArtifact={{ kind: "script", name: "check.sh", content: "echo ok" }}
        activeArtifactIndex={0}
        setActiveArtifactIndex={noop}
        addArtifact={noop}
        removeArtifact={noop}
        updateArtifact={noop}
        updateArtifactTask={noop}
        addArtifactTask={noop}
        removeArtifactTask={noop}
        onMaterialFiles={noop}
        telegramEnabled={false}
        setTelegramEnabled={noop}
        telegramChatId=""
        setTelegramChatId={noop}
      />,
    );

    expect(screen.getByText("Материалы для агента")).toBeInTheDocument();
    expect(screen.getByText(/Сохраняются первые 12 КБ текста/)).toBeInTheDocument();
    expect(screen.getByText(/отдельном ограниченном контейнере/)).toBeInTheDocument();
    expect(screen.getByText(/ограниченном Docker-контейнере/)).toBeInTheDocument();
    expect(screen.getByText(/обычным интернет-доступом/)).toBeInTheDocument();
    expect(screen.getByText(/не получает файлы, секреты, Docker socket или сеть хоста/)).toBeInTheDocument();
    expect(screen.getByText("Уведомить о результате в Telegram")).toBeInTheDocument();
  });
});
