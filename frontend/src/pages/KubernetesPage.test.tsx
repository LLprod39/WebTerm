import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import KubernetesPage from "@/pages/KubernetesPage";

describe("KubernetesPage", () => {
  it("renders the empty protected workspace without backend data", () => {
    render(
      <I18nProvider>
        <KubernetesPage />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Кубернетес" })).toBeInTheDocument();
    expect(screen.getByText("Пустая страница")).toBeInTheDocument();
  });
});
