import { lazy, Suspense, type ReactNode } from "react";
import type { RouteObject } from "react-router-dom";
import { NavigationLanding } from "@/layouts/NavigationLanding";
import { Guard } from "@/permissions/Guard";
import { LoadingState } from "@/components/ui";
import { usePermission } from "@/app/session";
import "./automation.css";
const PlaybookLibrary = lazy(() =>
  import("./PlaybookLibrary").then((m) => ({ default: m.PlaybookLibrary })),
);
const PlaybookWorkspace = lazy(() =>
  import("./PlaybookWorkspace").then((m) => ({ default: m.PlaybookWorkspace })),
);
const PipelineLibrary = lazy(() =>
  import("./Pipelines").then((m) => ({ default: m.PipelineLibrary })),
);
const PipelineWorkspace = lazy(() =>
  import("./Pipelines").then((m) => ({ default: m.PipelineWorkspace })),
);
const RunHistory = lazy(() =>
  import("./Runs").then((m) => ({ default: m.RunHistory })),
);
const PlaybookRunDetail = lazy(() =>
  import("./Runs").then((m) => ({ default: m.PlaybookRunDetail })),
);
const PipelineRunDetail = lazy(() =>
  import("./Runs").then((m) => ({ default: m.PipelineRunDetail })),
);
const DraftLibrary = lazy(() =>
  import("./DraftsSchedules").then((m) => ({ default: m.DraftLibrary })),
);
const DraftWorkspace = lazy(() =>
  import("./DraftsSchedules").then((m) => ({ default: m.DraftWorkspace })),
);
const Schedules = lazy(() =>
  import("./DraftsSchedules").then((m) => ({ default: m.Schedules })),
);
const SkillLibrary = lazy(() =>
  import("./Skills").then((m) => ({ default: m.SkillLibrary })),
);
const SkillWorkspace = lazy(() =>
  import("./Skills").then((m) => ({ default: m.SkillWorkspace })),
);
function protectedElement(feature: string, node: ReactNode) {
  return (
    <Guard feature={feature}>
      <Suspense fallback={<LoadingState />}>{node}</Suspense>
    </Guard>
  );
}
function RunGuard() {
  const automation = usePermission("automation");
  const runs = usePermission("studio_runs");
  return (
    <Guard
      feature={automation ? "automation" : runs ? "studio_runs" : "automation"}
    >
      <Suspense fallback={<LoadingState />}>
        <RunHistory />
      </Suspense>
    </Guard>
  );
}
export const automationRoutes: RouteObject[] = [
  { path: "automation", element: <NavigationLanding section="automation" /> },
  {
    path: "automation/playbooks",
    element: protectedElement("automation", <PlaybookLibrary />),
  },
  {
    path: "automation/playbooks/:id",
    element: protectedElement("automation", <PlaybookWorkspace />),
  },
  {
    path: "automation/pipelines",
    element: protectedElement("studio_pipelines", <PipelineLibrary />),
  },
  {
    path: "automation/pipelines/:id",
    element: protectedElement("studio_pipelines", <PipelineWorkspace />),
  },
  { path: "automation/runs", element: <RunGuard /> },
  {
    path: "automation/runs/playbook/:id",
    element: protectedElement("automation", <PlaybookRunDetail />),
  },
  {
    path: "automation/runs/pipeline/:id",
    element: protectedElement("studio_runs", <PipelineRunDetail />),
  },
  {
    path: "automation/drafts",
    element: protectedElement("studio_pipelines", <DraftLibrary />),
  },
  {
    path: "automation/drafts/:id",
    element: protectedElement("studio_pipelines", <DraftWorkspace />),
  },
  {
    path: "automation/schedules",
    element: protectedElement("studio_pipelines", <Schedules />),
  },
  {
    path: "intelligence/skills",
    element: protectedElement("studio_skills", <SkillLibrary />),
  },
  {
    path: "intelligence/skills/:slug",
    element: protectedElement("studio_skills", <SkillWorkspace />),
  },
];
