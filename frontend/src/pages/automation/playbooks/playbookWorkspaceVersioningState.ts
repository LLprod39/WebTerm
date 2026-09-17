import type { PlaybookCapabilities, PlaybookDetail, PlaybookDraft } from "@/api/playbooks";

import {
  isSourceBackedPlaybook,
  type PlaybookEditorState,
} from "../playbookEditorState";

export const draftKey = (playbookId: number | null) =>
  ["playbook-workspace", "draft", playbookId] as const;

export const revisionsKey = (playbookId: number | null) =>
  ["playbook-workspace", "revisions", playbookId] as const;

export const bindingsKey = (playbookId: number | null) =>
  ["playbook-workspace", "bindings", playbookId] as const;

export const sharesKey = (playbookId: number | null) =>
  ["playbook-workspace", "shares", playbookId] as const;

export function buildDraftContentPayload(editor: PlaybookEditorState, expectedVersion: number) {
  if (isSourceBackedPlaybook(editor)) {
    return {
      expected_version: expectedVersion,
      content_format: "ansible_yaml" as const,
      source_yaml: editor.sourceYaml,
    };
  }
  return {
    expected_version: expectedVersion,
    content_format: "runbook_json" as const,
    tasks: editor.tasks.filter((task) => task.command.trim()),
  };
}

export function inferPlaybookCapabilities(args: {
  playbook: PlaybookDetail | null;
  currentUserId: number | null;
  draftAccessible: boolean;
  bindingsAccessible: boolean;
  sharesAccessible: boolean;
}): PlaybookCapabilities {
  const provided = args.playbook?.capabilities;
  if (provided) return provided;
  const isOwner = Boolean(args.playbook && args.currentUserId && args.playbook.owner_id === args.currentUserId);
  const canEdit = isOwner || args.draftAccessible;
  const canShare = isOwner || args.sharesAccessible;
  return {
    can_view: Boolean(args.playbook),
    can_edit: canEdit,
    can_validate: canEdit,
    can_publish: isOwner || canShare,
    // Conservative fallback: binding access without draft access identifies an operator.
    can_run: isOwner || canShare || (!canEdit && args.bindingsAccessible),
    can_export: Boolean(args.playbook),
    can_share: canShare,
    can_delete: isOwner,
    is_owner: isOwner,
  };
}

export type DraftQueryPayload = { success: true; draft: PlaybookDraft };
