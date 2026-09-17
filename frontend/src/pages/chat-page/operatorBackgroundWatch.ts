/** Session-scoped watches for operator turns that continue after leaving /chat. */

const STORAGE_KEY = "webterm.operator.backgroundWatch.v1";

export type OperatorBackgroundWatch = {
  chatId: number;
  title: string;
  /** Highest assistant message id known when watching started. */
  baselineAssistantMessageId: number;
  watchedAt: number;
};

function readAll(): OperatorBackgroundWatch[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as OperatorBackgroundWatch[];
    return Array.isArray(parsed) ? parsed.filter((item) => Number.isFinite(item?.chatId)) : [];
  } catch {
    return [];
  }
}

function writeAll(items: OperatorBackgroundWatch[]) {
  try {
    if (!items.length) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore quota / private-mode failures.
  }
}

export function listOperatorBackgroundWatches(): OperatorBackgroundWatch[] {
  return readAll();
}

export function watchOperatorChat(input: {
  chatId: number;
  title?: string;
  baselineAssistantMessageId?: number;
}): void {
  const chatId = Number(input.chatId);
  if (!Number.isFinite(chatId) || chatId <= 0) return;
  const current = readAll().filter((item) => item.chatId !== chatId);
  current.push({
    chatId,
    title: String(input.title || "").trim() || `Chat ${chatId}`,
    baselineAssistantMessageId: Math.max(0, Number(input.baselineAssistantMessageId) || 0),
    watchedAt: Date.now(),
  });
  writeAll(current);
}

export function unwatchOperatorChat(chatId: number): void {
  const id = Number(chatId);
  if (!Number.isFinite(id)) return;
  writeAll(readAll().filter((item) => item.chatId !== id));
}

export function previewOperatorReply(text: string, maxLen = 140): string {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  if (!compact) return "";
  if (compact.length <= maxLen) return compact;
  return `${compact.slice(0, Math.max(0, maxLen - 1)).trimEnd()}…`;
}
