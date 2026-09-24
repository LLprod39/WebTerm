import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";

import { AiQuestionCard, splitQuestionContent } from "./AiQuestionCard";
import type { AiMessage } from "./ai-types";

describe("splitQuestionContent", () => {
  it("prefers explicit cmd and strips it from prose", () => {
    const { prose, cmd } = splitQuestionContent(
      "Нужно подтвердить: sudo docker ps -a",
      "sudo docker ps -a",
    );
    expect(cmd).toBe("sudo docker ps -a");
    expect(prose).toMatch(/Нужно подтвердить/);
    expect(prose).not.toContain("sudo docker");
  });

  it("extracts backtick command", () => {
    const { prose, cmd } = splitQuestionContent(
      "Разрешите запуск `sudo docker ps -a --format '{{.Names}}'` пожалуйста",
    );
    expect(cmd).toContain("sudo docker ps");
    expect(prose).toMatch(/Разрешите запуск/);
  });
});

function renderCard(msg: Partial<AiMessage>, onReply = vi.fn()) {
  const full: AiMessage = {
    id: "q1",
    role: "system",
    type: "question",
    content: msg.question || msg.content || "",
    qId: "qid-1",
    question: "Confirm sudo command",
    questionSource: "agent",
    questionOptions: [
      { label: "Разрешить один раз", value: "allow_once", description: "Только этот вызов" },
      { label: "Заблокировать", value: "block", description: "Не выполнять" },
    ],
    questionFreeTextAllowed: true,
    ...msg,
  };
  render(
    <I18nProvider>
      <AiQuestionCard msg={full} onReply={onReply} />
    </I18nProvider>,
  );
  return { onReply };
}

describe("AiQuestionCard", () => {
  it("renders a minimal confirm with command and flat actions", () => {
    renderCard({
      question:
        "Это safety-gate для сложной команды на nikitavm. Sudo уже разрешён, но этот вызов всё равно нужно подтвердить вручную потому что pipeline длинный.",
      questionCmd: "sudo docker ps -a",
    });

    expect(screen.getByText("Требуется ответ")).toBeInTheDocument();
    expect(screen.getByText(/\$ sudo docker ps -a/)).toBeInTheDocument();
    // Long prose hidden when cmd + options present.
    expect(screen.queryByText(/safety-gate/i)).not.toBeInTheDocument();
    // No nested chrome labels.
    expect(screen.queryByText("Команда")).not.toBeInTheDocument();
    expect(screen.queryByText(/Выберите вариант/i)).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Разрешить один раз" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Заблокировать" })).toBeInTheDocument();
  });

  it("collapses to a single receipt line after answer", () => {
    renderCard({
      question: "Approve?",
      questionAnswered: true,
      questionAnswer: "allow_once",
    });

    expect(screen.getByText("Разрешить один раз")).toBeInTheDocument();
    expect(screen.queryByText("Требуется ответ")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Заблокировать" })).not.toBeInTheDocument();
  });

  it("submits allow option on click", () => {
    const { onReply } = renderCard({
      question: "Approve?",
      questionCmd: "sudo true",
    });

    fireEvent.click(screen.getByRole("button", { name: "Разрешить один раз" }));
    expect(onReply).toHaveBeenCalledWith("qid-1", "allow_once");
  });
});
