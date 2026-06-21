import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import KubernetesPage from "@/pages/KubernetesPage";

describe("KubernetesPage", () => {
  it("renders the beta onboarding instead of an empty placeholder", () => {
    render(
      <I18nProvider>
        <KubernetesPage />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Kubernetes beta" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Подключение кластера" })).toBeInTheDocument();
    expect(screen.queryByText("Пустая страница")).not.toBeInTheDocument();
  });
});
