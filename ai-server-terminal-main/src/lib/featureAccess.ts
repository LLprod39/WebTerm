import type { AuthUser, FeatureFlag, StudioSectionFeature } from "@/lib/api";

export const STUDIO_SECTION_FEATURES: StudioSectionFeature[] = [
  "studio_pipelines",
  "studio_runs",
  "studio_agents",
  "studio_skills",
  "studio_mcp",
  "studio_notifications",
];

type UserLike = Pick<AuthUser, "features"> | null | undefined;

export function hasFeatureAccess(user: UserLike, feature: FeatureFlag | string): boolean {
  if (!user) return false;
  if (STUDIO_SECTION_FEATURES.includes(feature as StudioSectionFeature)) {
    return Boolean(user.features[feature] || user.features.studio);
  }
  return Boolean(user.features[feature]);
}

export function hasAnyFeatureAccess(user: UserLike, features: Array<FeatureFlag | string>): boolean {
  return features.some((feature) => hasFeatureAccess(user, feature));
}

export function canAccessStudio(user: UserLike): boolean {
  return hasFeatureAccess(user, "studio") || hasAnyFeatureAccess(user, STUDIO_SECTION_FEATURES);
}
