import { describe, expect, it } from "vitest";

import type { AssistantAction } from "@/api";

import { formatActionCardDescription } from "./actionPreview";

function action(partial: Partial<AssistantAction> & Pick<AssistantAction, "action_type">): AssistantAction {
  return {
    id: 1,
    chat_id: 1,
    message_id: 2,
    title: "",
    description: "",
    status: "requires_confirmation",
    risk: "mutating",
    required_feature: "agents",
    requires_confirmation: true,
    input: {},
    result: {},
    error: "",
    target_url: "",
    created_at: "",
    updated_at: "",
    confirmed_at: null,
    completed_at: null,
    ...partial,
  };
}

describe("formatActionCardDescription", () => {
  it("humanizes English agent.create schema text in Russian", () => {
    const text = formatActionCardDescription(
      action({
        action_type: "agent.create",
        description: "Create a custom agent for deployment",
        input: { name: "Деплой ветки", goal: "Обновить сервис из main" },
      }),
      "ru",
    );
    expect(text).toBe("Создать агента «Деплой ветки» · Обновить сервис из main");
  });

  it("humanizes agent.run when description is empty", () => {
    expect(
      formatActionCardDescription(
        action({ action_type: "agent.run", input: { agent_id: 17 } }),
        "ru",
      ),
    ).toBe("Запустить агента #17");
  });

  it("keeps an already Russian description", () => {
    expect(
      formatActionCardDescription(
        action({
          action_type: "operator.run",
          description: "Проверить nginx на prod",
        }),
        "ru",
      ),
    ).toBe("Проверить nginx на prod");
  });
});
