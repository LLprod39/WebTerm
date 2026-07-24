import type { OperatorSessionLine } from "./operatorSessionTypes";

export const LAST_CHAT_KEY = "operator_last_chat_id";

export function newSessionLine(
  partial: Omit<OperatorSessionLine, "id" | "at"> & { id?: string; at?: number },
): OperatorSessionLine {
  return {
    id: partial.id || `L-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    at: partial.at || Date.now(),
    source: partial.source,
    kind: partial.kind,
    text: partial.text,
  };
}
