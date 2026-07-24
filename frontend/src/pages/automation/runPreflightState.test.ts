import { describe, expect, it } from "vitest";

import type { PlaybookBindingProfile } from "@/api/playbooks";
import {
  buildAdhocBindings,
  buildRunRequest,
  buildRunTargetContext,
  buildValidationPayload,
  parseExtraVarsJson,
  pruneAdhocBindingChoices,
} from "./runPreflightState";

describe("run preflight state", () => {
  it("parses typed JSON objects and rejects malformed or non-object input", () => {
    expect(parseExtraVarsJson('{"count":2,"enabled":true,"items":[1,2]}')).toEqual({
      value: { count: 2, enabled: true, items: [1, 2] },
      error: null,
    });
    expect(parseExtraVarsJson("[1,2]")).toEqual({ value: null, error: "object_required" });
    expect(parseExtraVarsJson('{"count":')).toEqual({ value: null, error: "invalid_json" });
  });

  it("uses profile mappings and variable names without any secret values", () => {
    const profile = {
      id: 9,
      name: "Production",
      is_default: true,
      selector_mappings: { web: { server_ids: [2, 1, 2], group_ids: [4] } },
      variable_values: { release_channel: "stable" },
      secret_variables: ["deploy_token"],
      options: {},
      version: 2,
      content_hash: "hash",
      updated_at: "2026-07-24T10:00:00Z",
    } satisfies PlaybookBindingProfile;
    const context = buildRunTargetContext({
      bindingProfile: profile,
      serverIds: [99],
      groupIds: [88],
      inventoryBindings: {},
      extraVars: { release: 42 },
    });

    expect(context).toEqual({
      bindingProfileId: 9,
      serverIds: [1, 2],
      groupIds: [4],
      inventoryBindings: { web: { server_ids: [1, 2], group_ids: [4] } },
      variableNames: ["deploy_token", "release", "release_channel"],
    });
    expect(JSON.stringify(buildValidationPayload(context))).not.toContain("stable");
  });

  it("builds the final run request from the same reviewed context", () => {
    const context = {
      bindingProfileId: null,
      serverIds: [1],
      groupIds: [],
      inventoryBindings: { web: { server_ids: [1], group_ids: [] } },
      variableNames: ["release"],
    };

    expect(buildRunRequest({
      revisionId: 12,
      validationId: 77,
      context,
      extraVars: { release: 42 },
      policy: {
        concurrency: 5,
        dryRun: false,
        become: true,
        tags: " deploy ",
        skipTags: " risky ",
        limit: " web ",
      },
    })).toEqual({
      revision_id: 12,
      validation_id: 77,
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      extra_vars: { release: 42 },
      concurrency: 5,
      dry_run: false,
      become: true,
      tags: "deploy",
      skip_tags: "risky",
      limit: "web",
      engine: "ansible",
    });
  });

  it("drops explicit bindings when their target is no longer selected", () => {
    expect(buildAdhocBindings(
      ["web", "db"],
      { web: "server:1", db: "group:4" },
      new Set([2]),
      new Set([5]),
    )).toEqual({});

    expect(pruneAdhocBindingChoices(
      { web: "server:1", db: "group:4", all: "selected" },
      new Set([2]),
      new Set([5]),
    )).toEqual({ all: "selected" });
  });
});
