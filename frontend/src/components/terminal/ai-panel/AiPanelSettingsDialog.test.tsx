import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { DEFAULT_AI_SETTINGS } from "../ai-preferences";
import { AiPanelSettingsDialog } from "./AiPanelSettingsDialog";

describe("AiPanelSettingsDialog", () => {
  it("renders localized settings without relying on a global lang variable", () => {
    render(
      <I18nProvider>
        <AiPanelSettingsDialog
          open
          onOpenChange={vi.fn()}
          chatModeControl={<button type="button">Диалог</button>}
          executionModeControl={<button type="button">Выполнение</button>}
          settings={DEFAULT_AI_SETTINGS}
          onSettingsPatch={vi.fn()}
        />
      </I18nProvider>,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Настройки ИИ" })).toBeInTheDocument();
  });
});
