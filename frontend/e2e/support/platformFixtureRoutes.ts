import { handleKubernetesMockRequest } from "./platformFixtureKubernetes";
import { handlePluginMockRequest } from "./platformFixturePlugins";
import type { PlatformFixtureContext } from "./platformFixtureState";
import { handleAccessFixture } from "./platform-fixtures/access";
import { handleAgentsFixture } from "./platform-fixtures/agents";
import { handleAuthFixture } from "./platform-fixtures/auth";
import { handleDemoDataFixture } from "./platform-fixtures/demoData";
import { handleMarsFixture } from "./platform-fixtures/mars";
import { handleServersBootstrapFixture } from "./platform-fixtures/servers";
import { handleSettingsFixture } from "./platform-fixtures/settings";
import { handleStudioFixture } from "./platform-fixtures/studio";

/**
 * Platform mock API router for e2e harness.
 * Domain handlers are tried in the original match order — do not reorder.
 */
export function handlePlatformMockRequest(req: any, ctx: PlatformFixtureContext) {
  const { options } = ctx;

  const demoData = handleDemoDataFixture(req, ctx);
  if (demoData !== undefined) return demoData;

  const auth = handleAuthFixture(req, ctx);
  if (auth !== undefined) return auth;

  const kubernetesResponse = handleKubernetesMockRequest(req, options);
  if (kubernetesResponse) return kubernetesResponse;

  const servers = handleServersBootstrapFixture(req, ctx);
  if (servers !== undefined) return servers;

  const mars = handleMarsFixture(req, ctx);
  if (mars !== undefined) return mars;

  const agents = handleAgentsFixture(req, ctx);
  if (agents !== undefined) return agents;

  const studio = handleStudioFixture(req, ctx);
  if (studio !== undefined) return studio;

  const pluginResponse = handlePluginMockRequest(req);
  if (pluginResponse) return pluginResponse;

  const settings = handleSettingsFixture(req, ctx);
  if (settings !== undefined) return settings;

  const access = handleAccessFixture(req, ctx);
  if (access !== undefined) return access;
}
