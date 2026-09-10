export interface CompatibilityBase {
  path: string;
  content_hash: string;
  draft_version: number | null;
  bundle_hash: string;
  base_revision_id: number | null;
}
export function compatibilityExpectation(base: CompatibilityBase) {
  return {
    path: base.path,
    expected_content_hash: base.content_hash,
    expected_draft_version: base.draft_version,
    expected_bundle_hash: base.bundle_hash,
    base_revision_id: base.base_revision_id,
  };
}
