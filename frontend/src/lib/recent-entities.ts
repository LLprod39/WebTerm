/**
 * Lightweight recent-entities store for command palette / empty-state starters.
 * Persists last N servers and agent runs in localStorage.
 */

const RECENT_SERVERS_KEY = "webterm.recent.servers";
const RECENT_RUNS_KEY = "webterm.recent.runs";
const MAX_ITEMS = 5;

export type RecentServer = {
  id: number;
  name: string;
  host?: string;
  at: number;
};

export type RecentRun = {
  id: number;
  agentName: string;
  at: number;
};

function readList<T>(key: string): T[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function writeList<T>(key: string, items: T[]) {
  try {
    localStorage.setItem(key, JSON.stringify(items.slice(0, MAX_ITEMS)));
  } catch {
    // ignore quota / private mode
  }
}

export function getRecentServers(): RecentServer[] {
  return readList<RecentServer>(RECENT_SERVERS_KEY);
}

export function pushRecentServer(server: { id: number; name: string; host?: string }) {
  const next = [
    { id: server.id, name: server.name, host: server.host, at: Date.now() },
    ...getRecentServers().filter((item) => item.id !== server.id),
  ];
  writeList(RECENT_SERVERS_KEY, next);
}

export function getRecentRuns(): RecentRun[] {
  return readList<RecentRun>(RECENT_RUNS_KEY);
}

export function pushRecentRun(run: { id: number; agentName: string }) {
  const next = [
    { id: run.id, agentName: run.agentName, at: Date.now() },
    ...getRecentRuns().filter((item) => item.id !== run.id),
  ];
  writeList(RECENT_RUNS_KEY, next);
}
