export type ScopedPendingUser = {
  chatId: number | null;
  text: string;
  epoch: number;
  baselineIds: number[];
};

export type ScopedPendingSend = {
  chatId: number | null;
  text: string;
  epoch: number;
};

export type ScopedPendingMap<T> = Record<string, T>;

export function pendingChatKey(chatId: number | null) {
  return chatId == null ? "new" : `chat-${chatId}`;
}

export function getScopedPending<T>(pending: ScopedPendingMap<T>, chatId: number | null) {
  return pending[pendingChatKey(chatId)] ?? null;
}

export function setScopedPending<T>(
  pending: ScopedPendingMap<T>,
  chatId: number | null,
  value: T | null,
) {
  const key = pendingChatKey(chatId);
  if (value == null) {
    if (!(key in pending)) return pending;
    const next = { ...pending };
    delete next[key];
    return next;
  }
  return { ...pending, [key]: value };
}

/** Move optimistic/queued state created before the server assigned a chat id. */
export function promotePendingChat<T extends { chatId: number | null }>(
  pending: ScopedPendingMap<T>,
  chatId: number,
) {
  const temporary = getScopedPending(pending, null);
  if (!temporary) return pending;
  const withoutTemporary = setScopedPending(pending, null, null);
  return setScopedPending(withoutTemporary, chatId, { ...temporary, chatId });
}
