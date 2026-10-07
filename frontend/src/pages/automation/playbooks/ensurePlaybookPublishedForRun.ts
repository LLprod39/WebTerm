import {
  createPlaybookRevision,
  getPlaybookDraft,
  listPlaybookRevisions,
  publishPlaybookRevision,
} from "@/api/playbook-workspace";

/**
 * Ensures the playbook has a published revision ready for RunWizard.
 * Backend versioning stays intact — this only automates the ritual
 * (create revision → publish) so the operator never sees it.
 */
export async function ensurePlaybookPublishedForRun(playbookId: number): Promise<number> {
  const listed = await listPlaybookRevisions(playbookId);
  const publishedId = listed.published_revision_id;

  let draft: Awaited<ReturnType<typeof getPlaybookDraft>>["draft"] | null = null;
  try {
    draft = (await getPlaybookDraft(playbookId)).draft;
  } catch {
    if (publishedId) return publishedId;
    throw new Error("No published revision available");
  }

  const baseRevision = listed.revisions.find((item) => item.id === draft?.base_revision_id);
  const hasUnrevisionedChanges = Boolean(
    draft && (!baseRevision || draft.content_hash !== baseRevision.content_hash),
  );
  const hasUnpublishedRevision = Boolean(
    draft?.base_revision_id && draft.base_revision_id !== publishedId,
  );

  let revisionId: number | null =
    draft?.base_revision_id && draft.base_revision_id !== publishedId
      ? draft.base_revision_id
      : null;

  if (hasUnrevisionedChanges) {
    const created = await createPlaybookRevision(playbookId, {
      expected_version: draft.version,
      message: "Prepared for run",
    });
    revisionId = created.revision.id;
  } else if (!publishedId && draft.base_revision_id) {
    revisionId = draft.base_revision_id;
  } else if (hasUnpublishedRevision) {
    revisionId = draft.base_revision_id;
  }

  if (revisionId && revisionId !== publishedId) {
    const published = await publishPlaybookRevision(playbookId, revisionId);
    return published.published_revision_id;
  }

  if (publishedId) return publishedId;
  throw new Error("Nothing to publish for run");
}
