import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Link,
  Navigate,
  useParams,
  useRouteError,
} from "react-router-dom";
import AppShell from "@/layouts/AppShell";
import { Guard } from "@/permissions/Guard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { automationRoutes } from "@/features/automation/routes";
import { intelligenceRoutes } from "@/features/intelligence/routes";
import { governanceRoutes } from "@/features/governance/routes";
const Login = lazy(() => import("@/features/auth/LoginPage"));
const Servers = lazy(() => import("@/features/infrastructure/ServersPage"));
const ServerDetail = lazy(
  () => import("@/features/infrastructure/ServerDetailPage"),
);
const Terminal = lazy(() => import("@/features/infrastructure/TerminalPage"));
function TerminalRoute() {
  const { id } = useParams();
  return <Terminal key={id} />;
}
function RouteError() {
  const error = useRouteError();
  return (
    <main className="page-content">
      <ErrorState error={error} />
      <Link className="btn btn-secondary" to="/infrastructure/servers">
        Открыть серверы
      </Link>
    </main>
  );
}
export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <Suspense fallback={<LoadingState />}>
        <Login />
      </Suspense>
    ),
  },
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      {
        index: true,
        element: <Navigate to="/infrastructure/servers" replace />,
      },
      {
        path: "infrastructure/servers",
        element: (
          <Guard feature="servers">
            <Servers />
          </Guard>
        ),
      },
      {
        path: "infrastructure/servers/:id",
        element: (
          <Guard feature="servers">
            <ServerDetail />
          </Guard>
        ),
      },
      {
        path: "infrastructure/terminal/:id",
        element: (
          <Guard feature="servers">
            <TerminalRoute />
          </Guard>
        ),
      },
      ...automationRoutes,
      ...intelligenceRoutes,
      ...governanceRoutes,
      ...Object.entries({
        "dashboard/*": "/infrastructure/servers",
        "overview/*": "/infrastructure/servers",
        servers: "/infrastructure/servers",
        "monitoring/*": "/infrastructure/servers",
        "infrastructure/monitoring/*": "/infrastructure/servers",
        "kubernetes/*": "/infrastructure/servers",
        "infrastructure/kubernetes/*": "/infrastructure/servers",
        agents: "/intelligence/agents",
        chat: "/intelligence/chat",
        studio: "/automation/pipelines",
        "settings/users": "/governance/users",
        "settings/groups": "/governance/groups",
        "settings/permissions": "/governance/permissions",
      }).map(([path, to]) => ({ path, element: <Navigate to={to} replace /> })),
      {
        path: "*",
        element: (
          <EmptyState
            title="Страница не найдена"
            description="Проверьте адрес или выберите раздел в навигации."
            action={
              <Link className="btn btn-primary" to="/infrastructure/servers">
                Открыть серверы
              </Link>
            }
          />
        ),
      },
    ],
  },
]);
