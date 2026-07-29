/**
 * Authentication and session API.
 */
import { apiFetch } from "@/lib/api";
import type { FeatureFlag } from "@/lib/api";
import {
  canUseDemoMode,
  DEMO_SESSION,
  enableDemoMode,
  isDemoMode,
} from "@/lib/demo";

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser?: boolean;
  access_profile?: string;
  permission_sources?: Record<string, string>;
  features: Record<FeatureFlag, boolean> & Partial<Record<string, boolean>>;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: AuthUser | null;
}

export interface AuthLoginResponse {
  success: boolean;
  authenticated: boolean;
  next_url: string;
  user: AuthUser;
}

export async function fetchAuthSession(): Promise<AuthSessionResponse> {
  if (isDemoMode()) return DEMO_SESSION;
  try {
    return await apiFetch<AuthSessionResponse>("/api/auth/session/");
  } catch {
    if (canUseDemoMode() && enableDemoMode()) {
      return DEMO_SESSION;
    }
    return { authenticated: false, user: null };
  }
}

export async function authLogin(username: string, password: string, authMode: "auto" | "local" = "auto") {
  return apiFetch<AuthLoginResponse>("/api/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password, auth_mode: authMode }),
    timeoutMs: 10_000,
  });
}

export async function authLogout() {
  return apiFetch<{ success: boolean }>("/api/auth/logout/", { method: "POST" });
}
