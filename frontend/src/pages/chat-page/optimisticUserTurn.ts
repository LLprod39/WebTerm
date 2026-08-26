/**
 * A pending optimistic row can be replaced without ever becoming null (for
 * example, retry B is sent during the terminal grace period of failed A).
 * The explicit send epoch distinguishes that from an ordinary rerender and
 * also handles identical consecutive prompts.
 */
export function isNewOptimisticUserTurn({
  pendingText,
  wasPresent,
  previousEpoch,
  nextEpoch,
}: {
  pendingText: string | null;
  wasPresent: boolean;
  previousEpoch: number;
  nextEpoch: number;
}) {
  return Boolean(pendingText) && (!wasPresent || previousEpoch !== nextEpoch);
}
