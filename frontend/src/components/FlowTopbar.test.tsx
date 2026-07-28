import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { FlowTopbar } from "@/components/FlowTopbar";

vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatusDot: () => null }));
vi.mock("@/components/FlowChrome", () => ({ openCommandPalette: vi.fn() }));
vi.mock("@/components/NotificationCenter", () => ({ NotificationCenter: () => null }));
vi.mock("@/components/ui/sidebar", () => ({ SidebarTrigger: () => null }));
vi.mock("@/lib/i18n", () => ({
  localize: (_lang: string, _ru: string, en: string) => en,
  useI18n: () => ({
    lang: "en",
    t: (key: string) => ({ "nav.playbooks": "Ansible" })[key] ?? key,
  }),
}));
vi.mock("@/lib/ui-style", () => ({
  useUiStyle: () => ({ style: "flow", setStyle: vi.fn() }),
}));

describe("FlowTopbar automation breadcrumb", () => {
  it("labels /automation as Ansible", () => {
    render(
      <MemoryRouter initialEntries={["/automation"]}>
        <FlowTopbar />
      </MemoryRouter>,
    );

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByText("Ansible")).toBeInTheDocument();
  });
});
