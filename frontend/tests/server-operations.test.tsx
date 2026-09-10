import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import type { ServerDetail } from "@/api/infrastructure";
import type { LinuxSnapshots } from "@/api/server-operations";
import { ServerOperations } from "@/features/infrastructure/ServerOperations";

const api = vi.hoisted(() => ({ snapshot: vi.fn(), action: vi.fn() }));
vi.mock("@/api/server-operations", () => ({ serverOperationsApi: api }));
vi.mock("@/app/session", () => ({
  useSession: () => ({ user: { is_staff: true, features: { servers: true } } }),
}));
// Navigation blocking has its own data-router tests; these tests exercise
// snapshots and mutations through a real query client and ordinary URL state.
vi.mock("@/features/automation/unsaved", () => ({
  useUnsavedEditsBlocker: () => ({ state: "unblocked" }),
}));

type Snapshot<K extends keyof LinuxSnapshots> = LinuxSnapshots[K] & {
  observed_at: string;
};
const observedAt = "2026-09-06T08:00:00Z";
const server: ServerDetail = {
  id: 91,
  name: "QA server",
  host: "127.0.0.1",
  username: "qa",
  port: 22392,
  server_type: "ssh",
  group_id: null,
  can_edit: true,
  has_trusted_host_keys: true,
  is_shared_server: false,
  ai_read_only: true,
  share_context_enabled: false,
  shared_by_username: "",
  auth_method: "password",
  key_path: "",
  tags: "qa",
  notes: "Synthetic fixture for component tests",
  corporate_context: "",
  is_active: true,
  sudo_auth_mode: "none",
  network_config: {},
  has_saved_password: false,
  has_saved_sudo_password: false,
  can_view_password: false,
  capabilities: { connect_terminal: true, execute_command: true },
  trusted_host_key_fingerprints: [],
};
const capabilities: Snapshot<"capabilities"> = {
  observed_at: observedAt,
  capabilities: {
    hostname: "qa-linux",
    current_user: "qa",
    os_name: "QA Linux",
    os_id: "qa",
    kernel: "6.1",
    is_systemd: true,
    package_manager: "apt",
    commands: {},
    available_apps: { overview: true, services: true, logs: true },
  },
};
const overview: Snapshot<"overview"> = {
  observed_at: observedAt,
  overview: {
    hostname: "retained-snapshot-host",
    current_user: "qa",
    home_path: "/home/qa",
    cwd: "/home/qa",
    os_name: "QA Linux",
    kernel: "6.1",
    uptime_seconds: 90000,
    process_count: 12,
    load: { one: 0.1, five: 0.2, fifteen: 0.3 },
    memory: { total_mb: 256, used_mb: 128, percent: 50 },
    disk: { mount: "/", total_gb: 4, used_gb: 1, percent: 25 },
  },
};
const services: Snapshot<"services"> = {
  observed_at: observedAt,
  services: [
    {
      unit: "qa.service",
      name: "qa",
      load: "loaded",
      active: "active",
      sub: "running",
      description: "QA service before refresh",
      health: "active",
      is_active: true,
      is_failed: false,
    },
  ],
  summary: { total: 1, active: 1, failed: 0, inactive: 0, other: 0 },
  limit: 120,
};
const mixedServices: Snapshot<"services"> = {
  ...services,
  services: [
    { ...services.services[0], description: "worker primary" },
    {
      ...services.services[0],
      unit: "qa-idle.service",
      name: "qa-idle",
      description: "worker idle",
      active: "inactive",
      sub: "dead",
      health: "inactive",
      is_active: false,
    },
    {
      ...services.services[0],
      unit: "qa-failed.service",
      name: "qa-failed",
      description: "worker failed",
      active: "failed",
      sub: "failed",
      health: "failed",
      is_active: false,
      is_failed: true,
    },
    {
      ...services.services[0],
      unit: "qa-maint.service",
      name: "qa-maint",
      description: "worker maintenance",
      active: "maintenance",
      sub: "dead",
      health: "inactive",
      is_active: false,
    },
    {
      ...services.services[0],
      unit: "qa-other.service",
      name: "qa-other",
      description: "scheduler",
    },
    {
      ...services.services[0],
      unit: "qa-other-failed.service",
      name: "qa-other-failed",
      description: "scheduler failed",
      active: "failed",
      sub: "failed",
      health: "failed",
      is_active: false,
      is_failed: true,
    },
  ],
  summary: { total: 6, active: 2, failed: 2, inactive: 2, other: 0 },
};
function logs(content: string): Snapshot<"logs"> {
  return {
    observed_at: observedAt,
    logs: {
      content,
      lines: 120,
      available: true,
      presets: [
        {
          key: "journal",
          label: "Системный журнал",
          description: "system journal",
          available: true,
        },
        {
          key: "syslog",
          label: "syslog",
          description: "text log",
          available: true,
        },
        {
          key: "service",
          label: "Журнал службы",
          description: "service log",
          available: true,
        },
      ],
    },
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
function mockResource<K extends keyof LinuxSnapshots>(
  kind: K,
  handler: (params: Record<string, string>) => Promise<Snapshot<K>>,
) {
  api.snapshot.mockImplementation(
    (_id: number, resource: string, params: Record<string, string>) => {
      if (resource === "capabilities") return Promise.resolve(capabilities);
      if (resource === kind) return handler(params);
      throw new Error(`Unexpected snapshot: ${resource}`);
    },
  );
}
const clients: QueryClient[] = [];
function renderOperations(system = "overview", targetServer = server) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          `/infrastructure/servers/91?tab=operations&system=${system}`,
        ]}
      >
        <ServerOperations server={targetServer} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
async function openServiceMenu(unit: string) {
  fireEvent.keyDown(
    screen.getByRole("button", { name: `Управление службой ${unit}` }),
    { key: "Enter" },
  );
  return screen.findByRole("menu");
}
function expectServiceRows(units: string[]) {
  for (const row of mixedServices.services) {
    if (units.includes(row.unit))
      expect(screen.getByText(row.unit)).toBeVisible();
    else expect(screen.queryByText(row.unit)).not.toBeInTheDocument();
  }
}
beforeEach(() => {
  api.snapshot.mockReset();
  api.action.mockReset();
});
afterEach(() => {
  cleanup();
  for (const client of clients.splice(0)) client.clear();
});

describe("server snapshots", () => {
  it("retains loaded state during a failed refresh and clears the warning after recovery", async () => {
    const refresh = deferred<Snapshot<"overview">>();
    const read = vi
      .fn<() => Promise<Snapshot<"overview">>>()
      .mockResolvedValueOnce(overview)
      .mockReturnValueOnce(refresh.promise)
      .mockResolvedValueOnce({
        ...overview,
        overview: { ...overview.overview, hostname: "recovered-host" },
      });
    mockResource("overview", read);
    renderOperations();
    await screen.findByText("retained-snapshot-host");

    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(screen.getByText("retained-snapshot-host")).toBeVisible();
    expect(screen.getByRole("button", { name: "Обновить" })).toBeDisabled();
    await act(async () => refresh.reject(new ApiError("SSH unavailable", 503)));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Показан последний полученный снимок",
    );
    expect(screen.getByText("retained-snapshot-host")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    await screen.findByText("recovered-host");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([401, 403])(
    "hides cached content after authorization failure %s",
    async (status) => {
      const read = vi
        .fn<() => Promise<Snapshot<"overview">>>()
        .mockResolvedValueOnce(overview)
        .mockRejectedValueOnce(new ApiError("Access revoked", status));
      mockResource("overview", read);
      renderOperations();
      await screen.findByText("retained-snapshot-host");
      fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
      await screen.findByRole("alert");
      expect(
        screen.queryByText("retained-snapshot-host"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Показан последний полученный снимок/),
      ).not.toBeInTheDocument();
    },
  );
});

describe("log request controls", () => {
  it("has one refresh action which reloads unchanged filters exactly once", async () => {
    const refresh = deferred<Snapshot<"logs">>();
    const read = vi
      .fn<(params: Record<string, string>) => Promise<Snapshot<"logs">>>()
      .mockResolvedValueOnce(logs("initial journal"))
      .mockReturnValueOnce(refresh.promise);
    mockResource("logs", read);
    renderOperations("logs");
    await screen.findByText("initial journal");
    expect(screen.getAllByRole("button", { name: "Обновить" })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(read).toHaveBeenLastCalledWith({
      source: "journal",
      service: "",
      lines: "120",
    });
    expect(screen.getByLabelText("Источник")).toBeDisabled();
    expect(screen.getByLabelText("Строк")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Обновить" })).toBeDisabled();
    await act(async () => refresh.resolve(logs("refreshed journal")));
    await screen.findByText("refreshed journal");
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("retains source choices on an uncached failure and retries the selected filters", async () => {
    const request = deferred<Snapshot<"logs">>();
    const read = vi
      .fn<(params: Record<string, string>) => Promise<Snapshot<"logs">>>()
      .mockResolvedValueOnce(logs("initial journal"))
      .mockReturnValueOnce(request.promise)
      .mockResolvedValueOnce(logs("retried syslog"));
    mockResource("logs", read);
    renderOperations("logs");
    await screen.findByText("initial journal");
    fireEvent.change(screen.getByLabelText("Источник"), {
      target: { value: "syslog" },
    });
    fireEvent.change(screen.getByLabelText("Строк"), {
      target: { value: "80" },
    });
    expect(read).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(
      screen.getByRole("option", { name: "Журнал службы" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Источник")).toHaveValue("syslog");
    await act(async () =>
      request.reject(new ApiError("Log request failed", 503)),
    );
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Источник")).toHaveValue("syslog");
    expect(
      screen.getByRole("option", { name: "Журнал службы" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Повторить" })).toHaveLength(
      1,
    );

    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await screen.findByText("retried syslog");
    expect(read).toHaveBeenCalledTimes(3);
    expect(read).toHaveBeenLastCalledWith({
      source: "syslog",
      service: "",
      lines: "80",
    });
  });

  it("submits visible edited filters after failure instead of retrying the old request", async () => {
    const read = vi
      .fn<(params: Record<string, string>) => Promise<Snapshot<"logs">>>()
      .mockResolvedValueOnce(logs("initial journal"))
      .mockRejectedValueOnce(new ApiError("Log request failed", 503))
      .mockResolvedValueOnce(logs("selected service log"));
    mockResource("logs", read);
    renderOperations("logs");
    await screen.findByText("initial journal");
    fireEvent.change(screen.getByLabelText("Источник"), {
      target: { value: "syslog" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    await screen.findByRole("alert");

    fireEvent.change(screen.getByLabelText("Источник"), {
      target: { value: "service" },
    });
    fireEvent.change(screen.getByLabelText("Имя службы"), {
      target: { value: "qa.service" },
    });
    fireEvent.change(screen.getByLabelText("Строк"), {
      target: { value: "240" },
    });
    expect(
      screen.queryByRole("button", { name: "Повторить" }),
    ).not.toBeInTheDocument();
    expect(read).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    await screen.findByText("selected service log");
    expect(read).toHaveBeenCalledTimes(3);
    expect(read).toHaveBeenLastCalledWith({
      source: "service",
      service: "qa.service",
      lines: "240",
    });
  });
});

describe("service filters and controls", () => {
  it("filters all service states consistently with the backend health summary", async () => {
    const read = vi.fn().mockResolvedValue(mixedServices);
    mockResource("services", read);
    renderOperations("services");
    await screen.findByText("qa.service");
    for (const [filter, expected] of [
      ["failed", ["qa-failed.service", "qa-other-failed.service"]],
      ["active", ["qa.service", "qa-other.service"]],
      ["inactive", ["qa-idle.service", "qa-maint.service"]],
      ["all", mixedServices.services.map((row) => row.unit)],
    ] as const) {
      fireEvent.change(
        screen.getByRole("combobox", { name: "Состояние служб" }),
        {
          target: { value: filter },
        },
      );
      expectServiceRows([...expected]);
    }
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("keeps the search term while changing state and clears search without clearing the filter", async () => {
    mockResource("services", async () => mixedServices);
    renderOperations("services");
    await screen.findByText("qa.service");
    const search = screen.getByRole("textbox", {
      name: "Имя или описание службы…",
    });
    const state = screen.getByRole("combobox", { name: "Состояние служб" });
    fireEvent.change(search, { target: { value: "worker" } });
    fireEvent.change(state, { target: { value: "active" } });
    expect(search).toHaveValue("worker");
    expectServiceRows(["qa.service"]);
    fireEvent.change(state, { target: { value: "inactive" } });
    expect(search).toHaveValue("worker");
    expectServiceRows(["qa-idle.service", "qa-maint.service"]);
    fireEvent.change(state, { target: { value: "failed" } });
    expect(search).toHaveValue("worker");
    expectServiceRows(["qa-failed.service"]);
    fireEvent.click(screen.getByRole("button", { name: "Очистить поиск" }));
    expect(search).toHaveValue("");
    expect(state).toHaveValue("failed");
    expectServiceRows(["qa-failed.service", "qa-other-failed.service"]);
  });

  it.each(["qa-idle.service", "qa-maint.service"])(
    "offers only Start for a stopped service %s",
    async (unit) => {
      mockResource("services", async () => mixedServices);
      renderOperations("services");
      await screen.findByText(unit);
      const menu = await openServiceMenu(unit);
      expect(within(menu).getAllByRole("menuitem")).toHaveLength(1);
      expect(
        within(menu).getByRole("menuitem", { name: "Запустить" }),
      ).toBeVisible();
      expect(api.action).not.toHaveBeenCalled();
    },
  );

  it("offers restart, reload and stop for a running service without Start", async () => {
    mockResource("services", async () => mixedServices);
    renderOperations("services");
    await screen.findByText("qa.service");
    const menu = await openServiceMenu("qa.service");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual(["Перезапустить", "Перечитать конфигурацию", "Остановить"]);
    expect(
      within(menu).queryByRole("menuitem", { name: "Запустить" }),
    ).not.toBeInTheDocument();
    expect(api.action).not.toHaveBeenCalled();
  });

  it("disables management without command permission but still opens readable service logs", async () => {
    api.snapshot.mockImplementation((_id: number, resource: string) => {
      if (resource === "capabilities") return Promise.resolve(capabilities);
      if (resource === "services") return Promise.resolve(services);
      if (resource === "services/logs")
        return Promise.resolve({
          observed_at: observedAt,
          service_logs: {
            service: "qa.service",
            source: "journalctl",
            lines: 120,
            content: "Readable service journal",
            available: true,
          },
        } satisfies Snapshot<"services/logs">);
      throw new Error(`Unexpected snapshot: ${resource}`);
    });
    renderOperations("services", {
      ...server,
      capabilities: { ...server.capabilities, execute_command: false },
    });
    await screen.findByText("qa.service");
    const control = screen.getByRole("button", {
      name: "Управление службой qa.service",
    });
    expect(control).toBeDisabled();
    expect(control).toHaveAttribute(
      "title",
      "Нет разрешения на выполнение команд",
    );
    fireEvent.click(control);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    const journal = screen.getByRole("button", { name: "Журнал" });
    expect(journal).toBeEnabled();
    fireEvent.click(journal);
    const drawer = await screen.findByRole("dialog", {
      name: "Журнал · qa.service",
    });
    expect(
      await within(drawer).findByText("Readable service journal"),
    ).toBeVisible();
    expect(api.snapshot).toHaveBeenCalledWith(
      91,
      "services/logs",
      { service: "qa.service", lines: "120" },
      expect.any(AbortSignal),
    );
    expect(api.action).not.toHaveBeenCalled();
  });

  it.each(["qa.service", "qa-other.service"])(
    "clears typed confirmation after cancelling Stop before reopening for %s",
    async (nextUnit) => {
      mockResource("services", async () => mixedServices);
      renderOperations("services");
      await screen.findByText("qa.service");
      const initialMenu = await openServiceMenu("qa.service");
      fireEvent.click(
        within(initialMenu).getByRole("menuitem", { name: "Остановить" }),
      );
      const first = await screen.findByRole("dialog", {
        name: "Остановить · qa.service",
      });
      fireEvent.change(within(first).getByRole("textbox"), {
        target: { value: "qa.service" },
      });
      expect(
        within(first).getByRole("button", { name: "Остановить" }),
      ).toBeEnabled();
      fireEvent.click(within(first).getByRole("button", { name: "Отмена" }));
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );

      const nextMenu = await openServiceMenu(nextUnit);
      fireEvent.click(
        within(nextMenu).getByRole("menuitem", { name: "Остановить" }),
      );
      const reopened = await screen.findByRole("dialog", {
        name: `Остановить · ${nextUnit}`,
      });
      expect(within(reopened).getByRole("textbox")).toHaveValue("");
      expect(
        within(reopened).getByRole("button", { name: "Остановить" }),
      ).toBeDisabled();
      expect(api.action).not.toHaveBeenCalled();
    },
  );
});

describe("operation result feedback", () => {
  it("reports mutation success without claiming a pending or failed refresh succeeded", async () => {
    const refresh = deferred<Snapshot<"services">>();
    const read = vi
      .fn<() => Promise<Snapshot<"services">>>()
      .mockResolvedValueOnce(services)
      .mockReturnValueOnce(refresh.promise);
    mockResource("services", read);
    api.action.mockResolvedValue({
      performed_at: observedAt,
      service_action: {
        success: true,
        output: "restart accepted",
        dangerous: false,
      },
    });
    renderOperations("services");
    await screen.findByText("QA service before refresh");
    const menu = await openServiceMenu("qa.service");
    fireEvent.click(
      within(menu).getByRole("menuitem", { name: "Перезапустить" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Перезапустить · qa.service",
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Перезапустить" }),
    );

    await screen.findByText("Операция выполнена.");
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(api.action).toHaveBeenCalledExactlyOnceWith(91, {
      kind: "services",
      target: "qa.service",
      action: "restart",
    });
    expect(screen.queryByText(/Состояние обновлено/)).not.toBeInTheDocument();
    expect(screen.getByText("QA service before refresh")).toBeVisible();
    await act(async () => refresh.reject(new ApiError("Refresh failed", 503)));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Показан последний полученный снимок",
    );
    expect(screen.getByText("Операция выполнена.")).toBeVisible();
    expect(screen.queryByText(/Состояние обновлено/)).not.toBeInTheDocument();
  });
});
