const FIRST_RUN_READINESS_KEY_VERSION = "v1";

export function firstRunReadinessStorageKey(userId: number) {
  return `webterm.first-run-readiness.${FIRST_RUN_READINESS_KEY_VERSION}.${userId}`;
}

export function hasSeenFirstRunReadiness(userId: number) {
  try {
    return window.localStorage.getItem(firstRunReadinessStorageKey(userId)) === "seen";
  } catch {
    return false;
  }
}

export function markFirstRunReadinessSeen(userId: number) {
  try {
    window.localStorage.setItem(firstRunReadinessStorageKey(userId), "seen");
  } catch {
    // Storage may be disabled; the readiness page remains available manually.
  }
}

export function safeFirstRunNextPath(value: string | null | undefined) {
  if (!value) return "/dashboard";
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return "/dashboard";
  }
  if (!decoded.startsWith("/") || decoded.startsWith("//") || decoded.includes("\\")) return "/dashboard";
  if (decoded.startsWith("/login") || decoded.startsWith("/settings/readiness")) return "/dashboard";
  return decoded;
}
