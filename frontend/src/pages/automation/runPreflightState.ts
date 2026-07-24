import type {
  PlaybookRunRequest,
  ValidatePlaybookRevisionPayload,
} from "@/api/playbook-preflight";
import type {
  PlaybookBindingProfile,
  PlaybookInventoryBindings,
} from "@/api/playbooks";

export interface RunPolicyOptions {
  concurrency: number;
  dryRun: boolean;
  become: boolean;
  tags: string;
  skipTags: string;
  limit: string;
}

export interface RunTargetContext {
  bindingProfileId: number | null;
  serverIds: number[];
  groupIds: number[];
  inventoryBindings: PlaybookInventoryBindings;
  variableNames: string[];
}

export type ExtraVarsParseError = "invalid_json" | "object_required" | null;

export function parseExtraVarsJson(source: string): {
  value: Record<string, unknown> | null;
  error: ExtraVarsParseError;
} {
  if (!source.trim()) return { value: {}, error: null };
  try {
    const parsed = JSON.parse(source) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: null, error: "object_required" };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch {
    return { value: null, error: "invalid_json" };
  }
}

export function buildRunTargetContext(args: {
  bindingProfile: PlaybookBindingProfile | null;
  serverIds: Iterable<number>;
  groupIds: Iterable<number>;
  inventoryBindings: PlaybookInventoryBindings;
  extraVars: Record<string, unknown>;
}): RunTargetContext {
  const inventoryBindings = args.bindingProfile?.selector_mappings || args.inventoryBindings;
  const serverIds = args.bindingProfile
    ? Object.values(inventoryBindings).flatMap((binding) => binding.server_ids || [])
    : Array.from(args.serverIds);
  const groupIds = args.bindingProfile
    ? Object.values(inventoryBindings).flatMap((binding) => binding.group_ids || [])
    : Array.from(args.groupIds);
  const profileVariableNames = args.bindingProfile
    ? [
        ...Object.keys(args.bindingProfile.variable_values || {}),
        ...(args.bindingProfile.secret_variables || []),
      ]
    : [];
  return {
    bindingProfileId: args.bindingProfile?.id || null,
    serverIds: normalizedIds(serverIds),
    groupIds: normalizedIds(groupIds),
    inventoryBindings: normalizedBindings(inventoryBindings),
    variableNames: Array.from(new Set([...profileVariableNames, ...Object.keys(args.extraVars)])).sort(),
  };
}

export function buildValidationPayload(context: RunTargetContext): ValidatePlaybookRevisionPayload {
  return {
    ...(context.bindingProfileId ? { binding_profile_id: context.bindingProfileId } : {}),
    server_ids: context.serverIds,
    group_ids: context.groupIds,
    inventory_bindings: context.inventoryBindings,
    variable_names: context.variableNames,
  };
}

export function buildRunRequest(args: {
  revisionId: number;
  validationId: number;
  context: RunTargetContext;
  extraVars: Record<string, unknown>;
  policy: RunPolicyOptions;
}): PlaybookRunRequest {
  return {
    revision_id: args.revisionId,
    validation_id: args.validationId,
    ...(args.context.bindingProfileId ? { binding_profile_id: args.context.bindingProfileId } : {}),
    server_ids: args.context.serverIds,
    group_ids: args.context.groupIds,
    inventory_bindings: args.context.inventoryBindings,
    extra_vars: args.extraVars,
    concurrency: args.policy.concurrency,
    dry_run: args.policy.dryRun,
    become: args.policy.become,
    tags: args.policy.tags.trim(),
    skip_tags: args.policy.skipTags.trim(),
    limit: args.policy.limit.trim(),
    engine: "ansible",
  };
}

export function bindingsComplete(selectors: string[], bindings: PlaybookInventoryBindings): boolean {
  return selectors.every((selector) => {
    const binding = bindings[selector];
    return Boolean(binding && ((binding.server_ids || []).length || (binding.group_ids || []).length));
  });
}

export function buildAdhocBindings(
  selectors: string[],
  choices: Record<string, string>,
  serverIds: Set<number>,
  groupIds: Set<number>,
): PlaybookInventoryBindings {
  const output: PlaybookInventoryBindings = {};
  selectors.forEach((selector) => {
    const choice = choices[selector] || (selectors.length === 1 ? "selected" : "");
    if (choice === "selected") {
      output[selector] = { server_ids: Array.from(serverIds), group_ids: Array.from(groupIds) };
      return;
    }
    if (choice.startsWith("server:")) {
      const serverId = Number(choice.slice(7));
      if (serverIds.has(serverId)) output[selector] = { server_ids: [serverId], group_ids: [] };
      return;
    }
    if (choice.startsWith("group:")) {
      const groupId = Number(choice.slice(6));
      if (groupIds.has(groupId)) output[selector] = { server_ids: [], group_ids: [groupId] };
    }
  });
  return output;
}

export function pruneAdhocBindingChoices(
  choices: Record<string, string>,
  serverIds: Set<number>,
  groupIds: Set<number>,
): Record<string, string> {
  const next = Object.fromEntries(
    Object.entries(choices).filter(([, choice]) => {
      if (choice.startsWith("server:")) return serverIds.has(Number(choice.slice(7)));
      if (choice.startsWith("group:")) return groupIds.has(Number(choice.slice(6)));
      return true;
    }),
  );
  return Object.keys(next).length === Object.keys(choices).length ? choices : next;
}

export function runtimeValueType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function normalizedIds(values: Iterable<number>): number[] {
  return Array.from(new Set(Array.from(values).filter((value) => Number.isInteger(value) && value > 0))).sort(
    (left, right) => left - right,
  );
}

function normalizedBindings(bindings: PlaybookInventoryBindings): PlaybookInventoryBindings {
  return Object.fromEntries(
    Object.entries(bindings).map(([selector, binding]) => [
      selector,
      {
        server_ids: normalizedIds(binding.server_ids || []),
        group_ids: normalizedIds(binding.group_ids || []),
      },
    ]),
  );
}
