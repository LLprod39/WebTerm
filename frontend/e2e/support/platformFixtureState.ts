import { makeAgentFixtureData } from "./platformFixtureAgents";
import { makeAgentRunFixtureData } from "./platformFixtureAgentRun";
import { makeServerDetailFixtures } from "./platformFixtureServerDetail";
import { makeSettingsFixtureData } from "./platformFixtureSettings";
import { makeStudioMarsFixtureData } from "./platformFixtureStudioMars";
import { makeSessionUser, PlatformMockOptions, ServerItem } from "./platformFixtureTypes";

export function makePlatformFixtureContext(options: PlatformMockOptions = {}) {
  const defaultUser = makeSessionUser(options.isStaff ?? false);
  defaultUser.features = {
    ...defaultUser.features,
    ...(options.features || {}),
  };
  const state = {
    authenticated: options.authenticated ?? true,
  };
  const groups = [{ id: 11, name: "Core", description: "Core services", color: "#3b82f6", role: "owner", can_edit: true }];
  const servers: ServerItem[] = [
    {
      id: 1,
      name: "Web-01",
      host: "10.0.0.11",
      port: 22,
      username: "root",
      server_type: "ssh",
      status: "online",
      group_id: 11,
      group_name: "Core",
      is_shared: false,
      can_edit: true,
      share_context_enabled: true,
      shared_by_username: "",
      terminal_path: "/servers/1/terminal",
      minimal_terminal_path: "/servers/1/terminal/minimal",
      last_connected: null,
    },
  ];
  return {
    options,
    defaultUser,
    state,
    groups,
    servers,
    nextServerId: 2,
    ...makeAgentFixtureData(),
    ...makeStudioMarsFixtureData(),
    ...makeAgentRunFixtureData(),
    ...makeSettingsFixtureData(),
    ...makeServerDetailFixtures(),
  };
}

export type PlatformFixtureContext = ReturnType<typeof makePlatformFixtureContext>;
