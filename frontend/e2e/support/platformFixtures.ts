import { Page } from "@playwright/test";
import { installApiHarness } from "./apiHarness";
import { handlePlatformMockRequest } from "./platformFixtureRoutes";
import { makePlatformFixtureContext } from "./platformFixtureState";
import type { PlatformMockOptions, PlatformMockResult } from "./platformFixtureTypes";

export type { PlatformMockOptions, PlatformMockResult } from "./platformFixtureTypes";

export async function installPlatformMocks(page: Page, options: PlatformMockOptions = {}): Promise<PlatformMockResult> {
  const ctx = makePlatformFixtureContext(options);
  const harness = await installApiHarness(page, (req) => handlePlatformMockRequest(req, ctx), options.lang ?? "en");
  return { harness, state: ctx.state };
}
