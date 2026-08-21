import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { FrontendServer } from "@/lib/api";
import { useServersListController } from "./useServersListController";

function server(overrides: Partial<FrontendServer> & Pick<FrontendServer, "id" | "name">): FrontendServer {
  return {
    id: overrides.id,
    name: overrides.name,
    host: "10.0.0.1",
    port: 22,
    username: "ubuntu",
    server_type: "ssh",
    status: "unknown",
    group_id: null,
    group_name: "",
    is_shared: false,
    can_edit: true,
    share_context_enabled: true,
    shared_by_username: "",
    terminal_path: `/servers/${overrides.id}/terminal`,
    minimal_terminal_path: `/servers/${overrides.id}/terminal/minimal`,
    last_connected: null,
    ...overrides,
  };
}

const servers: FrontendServer[] = [
  server({ id: 1, name: "api-prod-01", host: "10.0.1.10", username: "deploy", group_id: 10, group_name: "Web" }),
  server({
    id: 2,
    name: "db-primary",
    host: "10.0.2.20",
    username: "postgres",
    group_id: 20,
    group_name: "Databases",
    detected_os: "debian",
    detected_os_pretty: "Debian 13",
  }),
  server({ id: 3, name: "bastion-01", host: "10.0.0.5", username: "ops" }),
];

describe("useServersListController", () => {
  beforeEach(() => localStorage.clear());

  it("searches operational fields, not only the display name", () => {
    const { result } = renderHook(() => useServersListController(servers, "test-user"));

    act(() => result.current.setSearch("postgres"));
    expect(result.current.filtered.map((item) => item.id)).toEqual([2]);

    act(() => result.current.setSearch("Debian 13"));
    expect(result.current.filtered.map((item) => item.id)).toEqual([2]);

    act(() => result.current.setSearch("10.0.0.5"));
    expect(result.current.filtered.map((item) => item.id)).toEqual([3]);
  });

  it("filters named and ungrouped servers without changing their access scope", () => {
    const { result } = renderHook(() => useServersListController(servers, "test-user"));

    expect(result.current.groupOptions).toEqual([
      { label: "", value: "__ungrouped__" },
      { label: "Databases", value: "Databases" },
      { label: "Web", value: "Web" },
    ]);

    act(() => result.current.setGroupFilter("Databases"));
    expect(result.current.filtered.map((item) => item.id)).toEqual([2]);

    act(() => result.current.setGroupFilter("__ungrouped__"));
    expect(result.current.filtered.map((item) => item.id)).toEqual([3]);
  });
});
