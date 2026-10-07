import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MigrationBanner } from "./MigrationBanner";

describe("MigrationBanner", () => {
  it("renders RU copy and wires organize / dismiss", () => {
    const onOrganize = vi.fn();
    const onDismiss = vi.fn();
    render(<MigrationBanner lang="ru" onOrganize={onOrganize} onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toHaveTextContent(/слева направо/i);
    fireEvent.click(screen.getByRole("button", { name: /Выровнять слева направо/i }));
    expect(onOrganize).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Оставить как есть/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders EN copy and dismiss icon", () => {
    const onDismiss = vi.fn();
    render(<MigrationBanner lang="en" onOrganize={vi.fn()} onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toHaveTextContent(/Organize left-to-right/i);
    fireEvent.click(screen.getByRole("button", { name: /Dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
