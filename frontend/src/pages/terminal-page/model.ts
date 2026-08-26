import type { TerminalConnectionStatus } from "@/components/terminal/XTerminal";
import type { AiMessage } from "@/components/terminal/ai-types";
import type { FrontendServer } from "@/lib/api";

export interface Tab {
  id: string;
  serverId: number;
  name: string;
  sessionNumber: number;
  status: "connected" | "connecting" | "error";
}

export interface TabAiState {
  messages: AiMessage[];
  isGenerating: boolean;
}

export type SidePanelMode = "none" | "ai" | "files" | "ui";

let idSeq = 0;

export function nextId() {
  idSeq += 1;
  return String(idSeq);
}

export function createEmptyAiState(): TabAiState {
  return {
    messages: [],
    isGenerating: false,
  };
}

export function mapStatus(status: TerminalConnectionStatus): Tab["status"] {
  if (status === "connected") return "connected";
  if (status === "connecting") return "connecting";
  return "error";
}

export function findServer(servers: FrontendServer[], id: number) {
  return servers.find((server) => server.id === id);
}

function getNextSessionNumber(tabs: Tab[], serverId: number) {
  return tabs.reduce((max, tab) => {
    if (tab.serverId !== serverId) return max;
    return Math.max(max, tab.sessionNumber);
  }, 0) + 1;
}

export function createTab(server: FrontendServer, tabs: Tab[], tabId = nextId()): Tab {
  return {
    id: tabId,
    serverId: server.id,
    name: server.name,
    sessionNumber: getNextSessionNumber(tabs, server.id),
    status: "connecting",
  };
}

export function formatTabName(tab: Tab) {
  if (tab.sessionNumber <= 1) return tab.name;
  return `${tab.name} · ${tab.sessionNumber}`;
}
