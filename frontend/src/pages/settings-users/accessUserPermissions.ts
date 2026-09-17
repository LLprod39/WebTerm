import type { AccessFeatureOption, PermissionMode } from "./settingsUsersTypes";

export function createPermissionModes(
  features: AccessFeatureOption[],
  explicit?: Record<string, boolean>,
): Record<string, PermissionMode> {
  return Object.fromEntries(
    features.map((feature) => {
      const value = explicit?.[feature.value];
      return [feature.value, value === true ? "allow" : value === false ? "deny" : "inherit"];
    }),
  );
}

export function buildExplicitPayload(modes: Record<string, PermissionMode>) {
  return Object.fromEntries(
    Object.entries(modes).map(([feature, mode]) => [feature, mode === "inherit" ? null : mode === "allow"]),
  );
}

export function toggleId(source: number[], id: number) {
  return source.includes(id) ? source.filter((value) => value !== id) : [...source, id];
}
