import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { CodeEditor } from "./CodeEditor";

beforeAll(() => {
  Object.defineProperty(Range.prototype, "getClientRects", {
    configurable: true,
    value: () => [],
  });
});

describe("CodeEditor diagnostics", () => {
  it("reports parser error locations for invalid YAML", async () => {
    const onDiagnosticsChange = vi.fn();

    render(
      <div className="h-80">
        <CodeEditor
          content={"- hosts: all\n  tasks: [\n"}
          filename="playbook.yml"
          ariaLabel="YAML editor"
          onDiagnosticsChange={onDiagnosticsChange}
        />
      </div>,
    );

    await waitFor(
      () => {
        const diagnostics = onDiagnosticsChange.mock.calls.at(-1)?.[0] || [];
        expect(diagnostics).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ severity: "error", line: expect.any(Number), column: expect.any(Number) }),
          ]),
        );
      },
      { timeout: 2_000 },
    );
  });
});
