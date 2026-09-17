import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ManagedSecretInput } from "./ManagedSecretInput";

describe("ManagedSecretInput", () => {
  it("keeps configured credentials write-only and emits explicit rotation or revocation", () => {
    const onSetMany = vi.fn();

    render(
      <ManagedSecretInput
        data={{ bot_token_configured: true }}
        label="Bot token"
        lang="en"
        onSetMany={onSetMany}
        placeholder="Bot token"
        secretKey="bot_token"
      />,
    );

    const input = screen.getByLabelText("Bot token");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("placeholder", "••••••••");
    expect(screen.getByText("Stored securely")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "rotated-token" } });
    expect(onSetMany).toHaveBeenCalledWith({
      bot_token: "rotated-token",
      bot_token_clear: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove saved Bot token" }));
    expect(onSetMany).toHaveBeenCalledWith({
      bot_token: "",
      bot_token_clear: true,
      bot_token_configured: false,
    });
  });
});
