import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import {
  MutationDrawer,
  deleteConfirmation,
} from "@/features/kubernetes/Mutations";
import {
  kubernetesApi,
  type KubeSession,
  type KubeWorkflow,
  type ResourceTarget,
} from "@/api/kubernetes";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const session: KubeSession = {
  id: "session-1",
  mode: "write",
  status: "active",
  cluster_id: "cluster_1",
  cluster_name: "production",
  namespace: "payments",
  reason: "CHG-1",
  approval_ref: "CHG-1",
  approved_by: "reviewer",
  expires_at: "2099-01-01T00:00:00Z",
  allowed_verbs: ["dry_run_apply", "apply", "delete"],
  allowed_kinds: ["Deployment"],
  allowed_namespaces: ["payments"],
  created_by: "operator",
  created_at: "2026-09-02T00:00:00Z",
  post_review_required: false,
  post_review_status: "none",
};
const target: ResourceTarget = {
  api_version: "apps/v1",
  kind: "Deployment",
  resource: "deployments",
  namespace: "payments",
  name: "gateway",
};
const workflows: KubeWorkflow[] = ["apply_yaml", "dry_run_apply", "delete"].map(
  (id) => ({
    id,
    mode: "kubernetes_admin_write",
    available: true,
    requestable: true,
    mutates_state: id !== "dry_run_apply",
    blocked_reason: "",
    requirements: [],
  }),
);
function setup(
  kind: "apply" | "delete",
  override: Partial<KubeSession> = {},
  caps = workflows,
) {
  return render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MutationDrawer
          session={{ ...session, ...override }}
          target={target}
          kind={kind}
          workflows={caps}
          onClose={() => {}}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
describe("Kubernetes mutation boundaries", () => {
  it("requires a fresh dry-run for the exact edited manifest and a separate final confirmation", async () => {
    const write = vi
      .spyOn(kubernetesApi, "resourceWrite")
      .mockResolvedValueOnce({
        action: { id: "proof-1", status: "dry_run" },
        target,
        diff: { changes: [] },
      })
      .mockResolvedValueOnce({
        action: { id: "proof-2", status: "dry_run" },
        target,
        diff: { changes: [] },
      })
      .mockResolvedValueOnce({
        action: { id: "apply-1", status: "completed" },
      });
    setup("apply");
    fireEvent.change(screen.getByLabelText("Манифест YAML"), {
      target: { value: "apiVersion: apps/v1\nkind: Deployment" },
    });
    fireEvent.change(screen.getByLabelText("Причина изменения"), {
      target: { value: "Approved change CHG-1" },
    });
    expect(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    ).toBeDisabled();
    expect(write).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Проверить на сервере" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Проверить и продолжить" }),
      ).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Манифест YAML"), {
      target: {
        value:
          "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: gateway",
      },
    });
    expect(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Проверить на сервере" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Проверить и продолжить" }),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    );
    expect(write).toHaveBeenCalledTimes(2);
    fireEvent.click(
      screen.getByRole("button", { name: "Подтвердить выполнение" }),
    );
    await waitFor(() => expect(write).toHaveBeenCalledTimes(3));
    expect(write.mock.calls[2]).toEqual([
      "cluster_1",
      "apply",
      expect.objectContaining({
        session_id: "session-1",
        dry_run_action_id: "proof-2",
        manifest_yaml:
          "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: gateway",
        reason: "Approved change CHG-1",
      }),
    ]);
  });
  it("matches the exact destructive target and retains review on server rejection", async () => {
    const write = vi
      .spyOn(kubernetesApi, "resourceWrite")
      .mockRejectedValue(new Error("Session expired"));
    setup("delete");
    fireEvent.change(screen.getByLabelText("Причина изменения"), {
      target: { value: "Remove retired workload" },
    });
    const input = screen.getByLabelText(
      `Для удаления введите: ${deleteConfirmation(target)}`,
    );
    fireEvent.change(input, {
      target: { value: "delete Deployment payments/other" },
    });
    expect(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    ).toBeDisabled();
    fireEvent.change(input, { target: { value: deleteConfirmation(target) } });
    fireEvent.click(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    );
    expect(write).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Подтвердить выполнение" }),
    );
    await screen.findByText("Session expired");
    expect(
      screen.getByRole("button", { name: "Подтвердить выполнение" }),
    ).toBeVisible();
    expect(write).toHaveBeenCalledWith(
      "cluster_1",
      "delete",
      expect.objectContaining({
        confirmation: "delete Deployment payments/gateway",
      }),
    );
  });
  it("never enables apply for expired sessions or a disabled capability", () => {
    const write = vi.spyOn(kubernetesApi, "resourceWrite");
    setup(
      "apply",
      { status: "expired" },
      workflows.map((w) => ({
        ...w,
        available: false,
        blocked_reason: "Runtime disabled",
      })),
    );
    fireEvent.change(screen.getByLabelText("Манифест YAML"), {
      target: { value: "kind: Deployment" },
    });
    expect(
      screen.getByRole("button", { name: "Проверить на сервере" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Проверить и продолжить" }),
    ).toBeDisabled();
    expect(write).not.toHaveBeenCalled();
  });
});
