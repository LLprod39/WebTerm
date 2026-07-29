import { json } from "../apiHarness";
import { makeSessionUser } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Auth session/login/logout fixtures. */
export function handleAuthFixture(req: any, ctx: PlatformFixtureContext) {
  const { options, defaultUser, state } = ctx;
      if (req.path === "/api/auth/session/" && req.method === "GET") {
        return json({
          authenticated: state.authenticated,
          user: state.authenticated ? defaultUser : null,
        });
      }

      if (req.path === "/api/auth/login/" && req.method === "POST") {
        state.authenticated = true;
        return json({
          success: true,
          authenticated: true,
          next_url: "/servers",
          user: makeSessionUser(options.isStaff ?? false, String(req.body?.username || defaultUser.username)),
        });
      }

      if (req.path === "/api/auth/logout/" && req.method === "POST") {
        state.authenticated = false;
        return json({ success: true });
      }

  return undefined;
}
