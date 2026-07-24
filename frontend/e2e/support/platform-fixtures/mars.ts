import { json } from "../apiHarness";
import { FIXED_DATE } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Mars workspaces/projects/sessions/runs fixtures. */
export function handleMarsFixture(req: any, ctx: PlatformFixtureContext) {
  const { marsWorkspace, marsSession, marsRun, marsProjects } = ctx;
      if (req.path === "/api/mars/workspaces/" && req.method === "GET") {
        return json({ workspaces: [marsWorkspace] });
      }

      if (req.path === "/api/mars/projects/" && req.method === "GET") {
        return json({ projects: marsProjects });
      }

      if (req.path.match(/^\/api\/mars\/sessions\/\d+\/$/) && req.method === "GET") {
        return json({ session: marsSession, recommended_skills: [] });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/$/) && req.method === "GET") {
        return json({ run: marsRun });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/events\/$/) && req.method === "GET") {
        return json({
          events: [
            {
              id: 1,
              run_id: marsRun.id,
              event_type: "tests_completed",
              message: "Verification passed.",
              payload: {},
              created_at: FIXED_DATE,
            },
          ],
        });
      }
  return undefined;
}
