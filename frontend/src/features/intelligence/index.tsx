import { useLocation, type RouteObject } from "react-router-dom";
import { lazy, type ComponentType } from "react";
import { Guard } from "@/permissions/Guard";
const ProfilesPage = lazy(() =>
  import("./Profiles").then((m) => ({ default: m.ProfilesPage })),
);
const AgentsPage = lazy(() =>
  import("./Agents").then((m) => ({ default: m.AgentsPage })),
);
const AgentDetailPage = lazy(() =>
  import("./Agents").then((m) => ({ default: m.AgentDetailPage })),
);
const AgentRunPage = lazy(() =>
  import("./Agents").then((m) => ({ default: m.AgentRunPage })),
);
const ChatPage = lazy(() =>
  import("./Chat").then((m) => ({ default: m.ChatPage })),
);
const McpPage = lazy(() =>
  import("./McpMemory").then((m) => ({ default: m.McpPage })),
);
const MemoryPage = lazy(() =>
  import("./McpMemory").then((m) => ({ default: m.MemoryPage })),
);
const MarsPage = lazy(() =>
  import("./Mars").then((m) => ({ default: m.MarsPage })),
);
const MarsSessionPage = lazy(() =>
  import("./Mars").then((m) => ({ default: m.MarsSessionPage })),
);
const MarsRunPage = lazy(() =>
  import("./Mars").then((m) => ({ default: m.MarsRunPage })),
);
import "./intelligence.css";
function KeyedPage({ page: Page }: { page: ComponentType }) {
  const location = useLocation();
  return <Page key={location.pathname} />;
}
export const intelligenceRoutes: RouteObject[] = [
  {
    path: "intelligence/profiles",
    element: (
      <Guard feature="studio_agents">
        <KeyedPage page={ProfilesPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/agents",
    element: (
      <Guard feature="agents">
        <KeyedPage page={AgentsPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/agents/:id",
    element: (
      <Guard feature="agents">
        <KeyedPage page={AgentDetailPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/runs/:id",
    element: (
      <Guard feature="agents">
        <KeyedPage page={AgentRunPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/chat",
    element: (
      <Guard feature="chat">
        <KeyedPage page={ChatPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/chat/:id",
    element: (
      <Guard feature="chat">
        <KeyedPage page={ChatPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/mcp",
    element: (
      <Guard feature="studio_mcp">
        <KeyedPage page={McpPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/memory",
    element: (
      <Guard feature="servers">
        <KeyedPage page={MemoryPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/mars",
    element: (
      <Guard feature="mars">
        <KeyedPage page={MarsPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/mars/sessions/:id",
    element: (
      <Guard feature="mars">
        <KeyedPage page={MarsSessionPage} />
      </Guard>
    ),
  },
  {
    path: "intelligence/mars/runs/:id",
    element: (
      <Guard feature="mars">
        <KeyedPage page={MarsRunPage} />
      </Guard>
    ),
  },
];
