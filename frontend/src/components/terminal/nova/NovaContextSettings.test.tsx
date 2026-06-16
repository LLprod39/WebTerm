import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { DEFAULT_AI_SETTINGS } from "../ai-preferences";
import type { AiAssistantSettings } from "../ai-types";
import { NovaContextSettings } from "./NovaContextSettings";

function renderSettings(settings: Partial<AiAssistantSettings> = {}) {
  const onChange = vi.fn();
  render(
    <I18nProvider>
      <NovaContextSettings settings={{ ...DEFAULT_AI_SETTINGS, ...settings }} onChange={onChange} />
    </I18nProvider>,
  );
  return { onChange };
}

describe("NovaContextSettings", () => {
  it("renders sudo policy options and emits selected policy", () => {
    const { onChange } = renderSettings({ novaSudoPolicy: "disabled" });

    expect(screen.getByText("Доступ sudo для Nova")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Без sudo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Спросить/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Разрешено/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Спросить/i }));

    expect(onChange).toHaveBeenCalledWith({ novaSudoPolicy: "ask" });
  });
});
