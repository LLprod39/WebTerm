import { lazy, type ComponentType } from "react";
import { useLocation, type RouteObject } from "react-router-dom";
import { Guard } from "@/permissions/Guard";
import "./kubernetes.css";
const ClustersPage = lazy(() =>
  import("./Inventory").then((m) => ({ default: m.ClustersPage })),
);
const ClusterPage = lazy(() =>
  import("./Inventory").then((m) => ({ default: m.ClusterPage })),
);
const InventoryDetailPage = lazy(() =>
  import("./Inventory").then((m) => ({ default: m.InventoryDetailPage })),
);
const ReadinessPage = lazy(() =>
  import("./Inventory").then((m) => ({ default: m.ReadinessPage })),
);
const ProvidersPage = lazy(() =>
  import("./Providers").then((m) => ({ default: m.ProvidersPage })),
);
const SessionsPage = lazy(() =>
  import("./Sessions").then((m) => ({ default: m.SessionsPage })),
);
const ExplorerPage = lazy(() =>
  import("./Explorer").then((m) => ({ default: m.ExplorerPage })),
);
const ActivityPage = lazy(() =>
  import("./Activity").then((m) => ({ default: m.ActivityPage })),
);
const RequestsPage = lazy(() =>
  import("./Requests").then((m) => ({ default: m.RequestsPage })),
);
const RequestPage = lazy(() =>
  import("./Requests").then((m) => ({ default: m.RequestPage })),
);
const DeliveryPage = lazy(() =>
  import("./Delivery").then((m) => ({ default: m.DeliveryPage })),
);
const DeliveryDetailPage = lazy(() =>
  import("./Delivery").then((m) => ({ default: m.DeliveryDetailPage })),
);
function Keyed({ page: Page }: { page: ComponentType }) {
  const l = useLocation();
  return <Page key={l.pathname} />;
}
const route = (
  path: string,
  Page: ComponentType,
  staff = false,
): RouteObject => ({
  path: `infrastructure/kubernetes${path}`,
  element: (
    <Guard feature="kubernetes" staff={staff}>
      <Keyed page={Page} />
    </Guard>
  ),
});
export const kubernetesRoutes: RouteObject[] = [
  route("", ClustersPage),
  route("/clusters/:id", ClusterPage),
  route("/clusters/:clusterId/namespaces/:id", InventoryDetailPage),
  route("/resources/:kind/:id", InventoryDetailPage),
  route("/readiness", ReadinessPage),
  route("/providers", ProvidersPage, true),
  route("/sessions", SessionsPage),
  route("/explorer/:sessionId", ExplorerPage),
  route("/activity", ActivityPage),
  route("/requests", RequestsPage),
  route("/requests/:id", RequestPage),
  route("/delivery", DeliveryPage),
  route("/delivery/:kind/:id", DeliveryDetailPage),
];
