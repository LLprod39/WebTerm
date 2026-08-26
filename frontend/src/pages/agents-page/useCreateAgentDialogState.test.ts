import { describe, expect, it } from "vitest";

import {
  toggleAgentServerSelection,
  toggleAllAgentServers,
} from "./useCreateAgentDialogState";

describe("agent wizard server selection", () => {
  it("keeps multiple selected servers in every agent mode", () => {
    const first = toggleAgentServerSelection([], 11);
    const second = toggleAgentServerSelection(first, 22);

    expect(second).toEqual([11, 22]);
    expect(toggleAgentServerSelection(second, 11)).toEqual([22]);
  });

  it("selects and clears the complete server scope", () => {
    expect(toggleAllAgentServers([11], [11, 22, 33])).toEqual([11, 22, 33]);
    expect(toggleAllAgentServers([11, 22, 33], [11, 22, 33])).toEqual([]);
  });
});
