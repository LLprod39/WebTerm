/**
 * src/api/auth.ts — Authentication and session API.
 *
 * Migration target for the following functions from src/lib/api.ts:
 *   fetchAuthSession, login, logout, fetchCsrfToken, fetchWsToken
 *   fetchAuthSession, apiAuthLogin, apiAuthLogout
 *
 * Interfaces to migrate here:
 *   AuthUser, AuthSessionResponse, AuthLoginResponse
 *
 * Status: re-exported from src/api/index.ts (pending migration)
 */

// Re-export types that clearly belong to this domain.
// Once the functions are physically moved here, remove them from lib/api.ts.
export type { AuthUser, AuthSessionResponse, AuthLoginResponse } from "@/lib/api";
export { fetchAuthSession } from "@/lib/api";
