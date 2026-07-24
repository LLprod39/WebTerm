import { json } from "../apiHarness";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Access users/groups/permissions fixtures. */
export function handleAccessFixture(req: any, ctx: PlatformFixtureContext) {
  const { accessUsers, accessGroups, accessPermissions, accessGroupPermissions } = ctx;
      if (req.path === "/api/access/users/" && req.method === "GET") {
        return json({ users: accessUsers });
      }

      if (req.path === "/api/access/groups/" && req.method === "GET") {
        return json({ groups: accessGroups });
      }

      if (req.path === "/api/access/permissions/" && req.method === "GET") {
        return json({
          permissions: accessPermissions,
          features: [
            { value: "servers", label: "Servers" },
            { value: "settings", label: "Settings" },
            { value: "orchestrator", label: "Orchestrator" },
          ],
        });
      }

      if (req.path === "/api/access/group-permissions/" && req.method === "GET") {
        return json({
          permissions: accessGroupPermissions,
          features: [
            { value: "servers", label: "Servers" },
            { value: "settings", label: "Settings" },
            { value: "orchestrator", label: "Orchestrator" },
          ],
        });
      }
  return undefined;
}
