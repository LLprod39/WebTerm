import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Values } from "@/api/automation";
import { ApiError } from "@/api/client";
import { KeyValues, ValidationResult } from "./shared";
import { compatibilityExpectation } from "./compatibility";
import { pipelineValidationError } from "./validation";

describe("Automation request contracts", () => {
  it("routes server validation errors to all declared graph nodes without duplicating the message", () => {
    const message =
      "Node 'check-1' field 'check_value' is required for contains.";
    const validation = pipelineValidationError(
      new ApiError("Validation failed", 400, {
        details: [message],
        issues: [
          {
            message,
            code: "node_field_invalid",
            severity: "error",
            node_ids: ["check-1"],
          },
        ],
      }),
    );
    const select = vi.fn();
    render(<ValidationResult value={validation!} onNode={select} />);
    expect(screen.getAllByText(message)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "К узлу" }));
    expect(select).toHaveBeenCalledWith("check-1");
  });
  it("edits nested settings without converting booleans, IDs or objects into strings", () => {
    let submitted: Values = {};
    function Form() {
      const [values, setValues] = useState<Values>({
        policy: { enabled: true, retries: 2 },
        server_ids: [4, 9],
      });
      submitted = values;
      return (
        <KeyValues label="Настройки" value={values} onChange={setValues} />
      );
    }
    render(<Form />);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Настройки: policy: retries" }),
      { target: { value: "3" } },
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Настройки: policy: enabled" }),
    );
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Настройки: server_ids, 2" }),
      { target: { value: "12" } },
    );
    expect(submitted).toEqual({
      policy: { enabled: false, retries: 3 },
      server_ids: [4, 12],
    });
  });
  it("pins adaptation application to the reviewed file, draft, revision and bundle", () => {
    const snapshot = {
      path: "roles/web/tasks/main.yml",
      content_hash: "a".repeat(64),
      bundle_hash: "b".repeat(64),
      draft_version: 8,
      base_revision_id: 15,
    };
    expect(compatibilityExpectation(snapshot)).toEqual({
      path: "roles/web/tasks/main.yml",
      expected_content_hash: "a".repeat(64),
      expected_bundle_hash: "b".repeat(64),
      expected_draft_version: 8,
      base_revision_id: 15,
    });
  });
});
