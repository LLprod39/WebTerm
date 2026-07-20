import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AssistantAction } from "@/api";

import { ActionCard } from "./ChatMessageViews";


function dangerousAction(): AssistantAction {
  return {
    id: 42,
    chat_id: 1,
    message_id: 2,
    action_type: "operator.run_fanout",
    title: "Fan-out command",
    description: "Run uptime on the selected servers.",
    status: "requires_confirmation",
    risk: "mutating",
    required_feature: "servers",
    requires_confirmation: true,
    input: { command: "uptime", server_ids: [1, 2] },
    result: {},
    error: "",
    target_url: "",
    blast_radius: {
      server_ids: [1, 2],
      server_names: ["web-01", "web-02"],
      count: 2,
      typed_confirm_required: true,
      typed_confirm_token: "FANOUT",
      typed_confirm_hint: "Type FANOUT",
    },
    dry_run_preview: { command: "uptime" },
    undo_payload: {},
    async_run_ref: {},
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:00:00Z",
    confirmed_at: null,
    completed_at: null,
  };
}


describe("ActionCard", () => {
  it("requires the exact typed token and shows the frozen blast radius", () => {
    const onConfirm = vi.fn();
    render(
      <ActionCard
        action={dangerousAction()}
        isWorking={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText(/web-01, web-02/)).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: /подтвердить|confirm/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: /подтверждение|confirmation/i }), {
      target: { value: "FANOUT" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith(42, "FANOUT");
  });
});
