import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, type RouteObject } from "react-router-dom";
import { LoadingState } from "@/components/ui";
import { NavigationLanding } from "@/layouts/NavigationLanding";
import "./governance.css";

const UsersPage = lazy(() =>
  import("./AccessPages").then((module) => ({ default: module.UsersPage })),
);
const GroupsPage = lazy(() =>
  import("./AccessPages").then((module) => ({ default: module.GroupsPage })),
);
const PermissionsPage = lazy(() =>
  import("./AccessPages").then((module) => ({
    default: module.PermissionsPage,
  })),
);
const AiSettingsPage = lazy(() =>
  import("./AiPage").then((module) => ({ default: module.AiSettingsPage })),
);
const AuditPage = lazy(() =>
  import("./AuditPage").then((module) => ({ default: module.AuditPage })),
);
const PluginsPage = lazy(() =>
  import("./PluginsPage").then((module) => ({ default: module.PluginsPage })),
);
const GeneralSettingsPage = lazy(() =>
  import("./SettingsPages").then((module) => ({
    default: module.GeneralSettingsPage,
  })),
);
const IdentitySettingsPage = lazy(() =>
  import("./SettingsPages").then((module) => ({
    default: module.IdentitySettingsPage,
  })),
);
const LimitsSettingsPage = lazy(() =>
  import("./SettingsPages").then((module) => ({
    default: module.LimitsSettingsPage,
  })),
);
const ReadinessPage = lazy(() =>
  import("./SettingsPages").then((module) => ({
    default: module.ReadinessPage,
  })),
);
const page = (children: ReactNode) => (
  <div className="governance-page">
    <Suspense fallback={<LoadingState />}>{children}</Suspense>
  </div>
);
export const governanceRoutes: RouteObject[] = [
  { path: "governance/users", element: page(<UsersPage />) },
  { path: "governance/groups", element: page(<GroupsPage />) },
  { path: "governance/permissions", element: page(<PermissionsPage />) },
  { path: "governance/audit", element: page(<AuditPage />) },
  { path: "governance/plugins", element: page(<PluginsPage />) },
  {
    path: "governance/activity/*",
    element: <Navigate to="/infrastructure/servers" replace />,
  },
  {
    path: "settings/workspace/*",
    element: <Navigate to="/infrastructure/servers" replace />,
  },
  { path: "settings", element: <NavigationLanding section="settings" /> },
  {
    path: "settings/integrations",
    element: (
      <NavigationLanding
        section="settings"
        parentPath="/settings/integrations"
      />
    ),
  },
  { path: "settings/general", element: page(<GeneralSettingsPage />) },
  { path: "settings/ai", element: page(<AiSettingsPage />) },
  {
    path: "settings/access",
    element: <Navigate to="/governance/users" replace />,
  },
  { path: "settings/identity", element: page(<IdentitySettingsPage />) },
  { path: "settings/readiness", element: page(<ReadinessPage />) },
  { path: "settings/limits", element: page(<LimitsSettingsPage />) },
];
