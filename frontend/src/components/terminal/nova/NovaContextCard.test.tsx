import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";

import { NovaContextCard } from "./NovaContextCard";
import type { NovaContextPayload } from "../ai-types";

const sample: NovaContextPayload = {
  session: {
    cwd: "/home/nikita",
    user: "nikita",
    hostname: "nikitavm",
    shell: "/bin/bash",
    python: "/usr/bin/python3",
    source: "prompt",
  },
  recent_activity: [
    { command: "hostname", summary: "Checked hostname" },
    { command: "docker ps" },
  ],
};

function renderCard(context?: NovaContextPayload) {
  return render(
    <I18nProvider>
      <NovaContextCard context={context} />
    </I18nProvider>,
  );
}

describe("NovaContextCard", () => {
  it("renders a collapsed one-liner by default without nested session dump", () => {
    renderCard(sample);

    const toggle = screen.getByRole("button", { name: /Контекст Nova/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.textContent).toMatch(/nikita@nikitavm/);
    expect(toggle.textContent).toMatch(/\/home\/nikita/);
    expect(toggle.textContent).toMatch(/2 команд/);

    expect(screen.queryByText("/usr/bin/python3")).not.toBeInTheDocument();
    expect(screen.queryByText("Checked hostname")).not.toBeInTheDocument();
  });

  it("expands session and activity without nested card chrome", () => {
    renderCard(sample);

    fireEvent.click(screen.getByRole("button", { name: /Контекст Nova/i }));

    expect(screen.getByRole("button", { name: /Контекст Nova/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("/usr/bin/python3")).toBeInTheDocument();
    expect(screen.getByText("Checked hostname")).toBeInTheDocument();
    expect(screen.getByText("docker ps")).toBeInTheDocument();
  });

  it("returns nothing when context is empty", () => {
    const { container } = renderCard({});
    expect(container).toBeEmptyDOMElement();
  });
});
